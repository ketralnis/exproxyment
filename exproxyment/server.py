#!/usr/bin/env python2.7

from collections import namedtuple
import logging
import random
import json
import urllib

import tornado.ioloop
import tornado.web
import tornado.gen
import tornado.httpclient
import tornado.httputil
from tornado.ioloop import PeriodicCallback
from tornado.options import define, options, parse_command_line

from .utils import parse_backends, parse_weights
from .utils import unparse_backends, unparse_weights

logger = logging.getLogger(__name__)

define('port', type=int, default=7000)
define('backends', default='')
define('cookie_domain', default=None)
define('weights', default='')
define('soft_sticky', type=bool, default=True)
define('hard_sticky', type=bool, default=False)


class BackendState(namedtuple('BackendState', 'healthy version')):

    def __repr__(self):
        healthy = {
            None: 'unknown',
            True: 'healthy',
            False: 'unhealthy',
        }
        if self.healthy:
            return ("<BackendState %s v=%s>"
                    % (healthy[self.healthy], self.version))
        else:
            return ("<BackendState %s>"
                    % (healthy[self.healthy],))

    def to_json(self):
        return {'healthy': self.healthy,
                'version': self.version}


class Backend(namedtuple('Backend', 'host port')):

    def __repr__(self):
        return "<Backend %s:%d>" % (self.host, self.port)

    def to_json(self):
        return {'host': self.host,
                'port': self.port}


class ActiveRequest(namedtuple('ActiveRequest', ('source_host', 'uri',
                                                 'backend'))):

    def to_json(self):
        return {'source_host': self.source_host,
                'backend': self.backend.to_json(),
                'uri': self.uri}


class ServerState(object):

    def __init__(self, backends=None, weights=None):
        self.backends = backends or {}
        self.weights = weights or {}
        self.requests = set()

    def backend_for(self, version):
        backends = [backend
                    for (backend, state) in self.backends.iteritems()
                    if state.version == version]
        if backends:
            return random.choice(backends)
        return None

    def healthy(self, for_version=None):
        return any(state.healthy
                   for backend, state in self.backends.iteritems()
                   if for_version is None or for_version == state.version)

    def available_versions(self):
        return set(state.version for state in self.backends.values()
                   if state.healthy)

    def available_backends(self):
        return [backend for (backend, state) in self.backends.items()
                if state.healthy]

    def set_backends(self, backends):
        # make sure to inherit the previous state if we already knew about this
        # server, otherwise re-adding an existing backend will wipe out all of
        # the health checks we know about and we'll start returning 504s

        current_backends = self.backends
        self.backends = {}

        for backend in backends:
            self.backends[backend] = current_backends.get(backend,
                                                          BackendState(None, None))

    def add_backend(self, backend):
        self.backends[backend] = self.backends.get(backend,
                                                   BackendState(None, None))

    def remove_backend(self, backend):
        if backend in self.backends:
            del self.backends[backend]


# TODO need this global state to live somewhere. it's set in main()
server_state = ServerState()


class HealthDaemon(object):

    """
    Every second, check on every backend that's never been seen before, as well
    as one backend chosen at random
    """

    def __init__(self, ioloop, periodicity=1000):
        self.ioloop = ioloop
        self.check_count = 0
        self.periodic = PeriodicCallback(self.task, periodicity, self.ioloop)

    def start(self):
        self.periodic.start()

    @staticmethod
    def twofilter(pred, it):
        falses, trues = [], []
        for item in it:
            if pred(item):
                trues.append(item)
            else:
                falses.append(item)

        return falses, trues

    @tornado.gen.coroutine
    def task(self):
        self.check_count += 1

        unseen, seen = self.twofilter(
            lambda backend: server_state.backends[backend].healthy is not None,
            server_state.backends)

        futs = {}

        for backend in unseen:
            # if there's anyone we haven't ever seen before, fire off all of
            # those checks at once
            futs[backend] = self.health_check(backend)

        if seen:
            # also randomly check on the ones we've seen before
            backend = random.choice(seen)
            futs[backend] = self.health_check(backend)

        yield futs.values()

    @tornado.gen.coroutine
    def health_check(self, backend):
        oldstate = server_state.backends[backend]

        client = tornado.httpclient.AsyncHTTPClient()
        url = 'http://%s:%d/health' % (backend.host, backend.port)

        try:
            response = yield client.fetch(url,
                                          connect_timeout=500,
                                          request_timeout=500)
        except Exception as exc:
            code = 599
            if oldstate.healthy in (True, None):
                logger.warn("Bad connection to %r (%s)", backend, exc)
            else:
                logger.debug("Bad connection to %r (%s)", backend, exc)
        else:
            code = response.code

        if backend not in server_state.backends:
            # a server was removed while were in the process of checking on it.
            # disregard any health info that we got from it
            logger.debug("Backend %r disappeared while we were checking on it",
                         backend)
            return

        if code != 200:
            server_state.backends[backend] = BackendState(healthy=False,
                                                          version=None)
        else:
            body = json.loads(response.body)
            healthy = body.get('healthy', False)
            version = body.get('version', None)
            if healthy is not True or not version:
                logger.info("Unhealthy %r (%r:%r)", backend, healthy, version)
                server_state.backends[backend] = BackendState(healthy=False,
                                                              version=None)
            else:
                server_state.backends[backend] = BackendState(healthy=True,
                                                              version=version)

        if oldstate != server_state.backends[backend]:
            logger.warn("%r: %r -> %r",
                        backend, oldstate, server_state.backends[backend])
        else:
            logger.debug("%r: %r -> %r (%d)",
                         backend, oldstate, server_state.backends[backend],
                         code)


class BaseHandler(tornado.web.RequestHandler):

    def write_json(self, js):
        self.set_header('Content-Type', 'application/json; charset=utf-8')
        self.write(json.dumps(js))
        self.write('\n')

    def nope(self, reason, code=504):
        self.set_status(code)

        if isinstance(reason, dict):
            self.write_json(reason)
        else:
            self.write(reason)

        self.write('\n')


class ProxyHandler(BaseHandler):

    def requested_version(self):
        """
        Determine what version the user has requested and how strongly they feel
        about it

        returns a tuple of (Required, Version)
        """

        # header
        for required, headername in ((True, 'X-Exproxyment-Require-Version'),
                                     (False, 'X-Exproxyment-Request-Version')):
            version = self.request.headers.get(headername, None)
            if version:
                return required, version

        # get argument
        for required, getargname in ((True, 'exproxyment_require_version'),
                                     (False, 'exproxyment_request_version')):
            version = self.get_argument(getargname, None)
            if version:
                return required, version

        # cookie
        for required, cookiename in ((True, 'exproxyment_require_version'),
                                     (False, 'exproxyment_request_version')):
            version = self.request.cookies.get(cookiename)
            if version:
                value = version.value
                unquoted = urllib.unquote(value)
                asjson = json.loads(unquoted)
                version = asjson['version']
                return required, version

        return False, None

    def place_user(self):
        """
        the user either didn't ask for a particular version, or they nicely
        requested a version we couldn't give them. so we try to place them in
        a version bucket
        """

        available_versions = server_state.available_versions()

        if not server_state.weights:
            # the administrator hasn't given us any direction as to where they
            # want users placed, so let's just pick the "highest" version
            return max(available_versions)

        # otherwise take the weights the administrator gave us. TODO do a proper
        # random weighting, and try to find a way to make these stickier than
        # just cookies. also ketama instead of this nonsense
        choices = []
        for version in available_versions:
            choices.extend([version] * server_state.weights.get(version, 0))

        if choices:
            return random.choice(choices)

        return None

    @tornado.gen.coroutine
    def proxy(self, path, tries=3):
        if tries <= 0:
            self.nope('too many tries')
            return

        client = tornado.httpclient.AsyncHTTPClient()

        if not server_state.healthy():
            self.nope('no backends available')
            return

        required, version = self.requested_version()

        if version:
            logger.debug("User requested version %r (required:%r)",
                         version, required)

        if required and version not in server_state.available_versions():
            self.nope("no backend available for %s" % (version,))
            return

        if version not in server_state.available_versions():
            # otherwise rebucket them
            version = self.place_user()

        if not version:
            self.nope("no valid versions")
            return

        backend = server_state.backend_for(version)

        if not backend:
            self.nope('no backend for %r' % (version,))
            return

        client = tornado.httpclient.AsyncHTTPClient()
        uri = 'http://%s:%d/%s' % (backend.host, backend.port, path)
        method = self.request.method

        headers = tornado.httputil.HTTPHeaders()

        for header, value in self.request.headers.iteritems():
            headers.add(header, value)

        headers.add('X-Exproxyment-Version', version)

        body = None
        if method != 'GET':
            body = self.request.body

        active_request = ActiveRequest(source_host=self.request.remote_ip,
                                       uri=uri, backend=backend)
        server_state.requests.add(active_request)

        try:
            response = yield client.fetch(uri,
                                          method=method,
                                          headers=headers,
                                          body=body)

        except Exception as e:
            # TODO we can allow the client to specify whether
            # connection-refused type errors are retryable
            self.nope("bad connection to %r (%r)" % (backend, e))
            return

        finally:
            server_state.requests.remove(active_request)

        if (response.code == 406
                and response.headers.get('X-Exproxyment-Wrong-Version')):
            # they're telling us that they can't service this version, so they
            # want us to hit someone else
            ret = yield self.proxy(path, tries=tries - 1)
            raise tornado.gen.Return(ret)

        self.set_status(response.code)

        # copy all of the headers
        for header, value in response.headers.iteritems():
            self.set_header(header, value)

        # set our own headers
        self.set_header('X-Exproxyment-Version', version)
        self.set_header('X-Exproxyment-Backend',
                        "%s:%d" % (backend.host, backend.port))

        # set up the stickiness cookies if necessary
        if options.soft_sticky or options.hard_sticky:
            cookie_name = ('exproxyment_request_version'
                           if options.soft_sticky
                           else 'exproxyment_require_version')
            cookie_value = urllib.quote(json.dumps({'version': version}))
            self.set_cookie(cookie_name,
                            cookie_value,
                            options.cookie_domain or None)

        self.write(response.body)

    get = proxy
    post = proxy
    head = proxy
    put = proxy
    delete = proxy


class MyHealth(BaseHandler):

    """
    The health of the exproxyment daemon. We are healthy if we have at least one
    healthy backend for the requested version (or any healthy backends if no
    version is specified)
    """

    def get(self):
        for_version = self.get_argument('for_version', None)

        healthy = server_state.healthy(for_version)

        if not healthy:
            self.set_status(500)

        backends = []
        for backend, state in server_state.backends.iteritems():
            js = {}
            js.update(backend.to_json())
            js.update(state.to_json())
            backends.append(js)
        backends = sorted(backends,
                          key=lambda x: (x['host'],
                                         x['port']))

        ret = {
            'healthy': healthy,
            'versions': sorted(list(server_state.available_versions())),
            'weights': server_state.weights, # already jsonnable
            'backends': backends,
        }

        self.write_json(ret)


class ExproxymentConfigure(BaseHandler):

    """
    Replace the backends or version weighting configuration of a running sever
    """

    def get(self):
        self.write_json({'backends': [{'host': backend.host,
                                       'port': backend.port,
                                       'healthy': state.healthy,
                                       'version': state.version}
                                      for (backend, state)
                                      in server_state.backends.iteritems()],
                         'weights': server_state.weights})

    def post(self):
        body = json.loads(self.request.body)

        if 'backends' in body:
            try:
                new_backends = validate_backend_json(body['backends'])
            except ValueError:
                return self.nope({'error': 'bad format: backends'}, code=400)

            logger.info("Reconfiguring backends: %r", new_backends)
            server_state.set_backends(new_backends)

        if 'weights' in body:
            weights = body['weights']

            # validate the format of the new weights
            if not (isinstance(weights, dict)
                    and (isinstance(k, basestring)
                         and isinstance(v, (int, long))
                         for (k, v) in weights.items())):
                return self.nope('bad format: weights', code=400)

            logger.info("Reconfiguring weights: %r", weights)
            server_state.weights = weights

        return self.get()


class RegisterSelfHandler(BaseHandler):

    """
    Like ExproxymentConfigure but takes a list of *new* backends to register
    """

    def post(self):
        body = json.loads(self.request.body)

        try:
            backends = validate_backend_json(body['backends'])
        except (KeyError, ValueError):
            return self.nope('bad format: backends', code=400)

        for backend in backends:
            logger.info("Registering backend %r", backend)
            server_state.add_backend(backend)

        self.write_json({'status': 'ok'})


class DeregisterSelfHandler(BaseHandler):

    """
    Like RegisterSelfHandler but takes a list of backends to deregister
    """

    def post(self):
        body = json.loads(self.request.body)

        try:
            backends = validate_backend_json(body['backends'])
        except (KeyError, ValueError):
            return self.nope('bad format: backends', code=400)

        for backend in backends:
            logger.info("Deregistering backend %r", backend)
            server_state.remove_backend(backend)

        self.write_json({'status': 'ok'})


class ExproxymentActivity(BaseHandler):

    def get(self):
        activity = []

        for active_request in server_state.requests:
            activity.append(active_request.to_json())

        self.write_json({'activity': activity})


class FourOhFour(BaseHandler):

    def get(self, *a):
        self.set_status(404)


def validate_backend_json(backends):
    # validate the format of the servers TODO duplicated with above
    if not (isinstance(backends, list)
            and (isinstance(k, basestring)
                 and isinstance(v, basestring)
                 for (k, v)
                 in backends)):
        raise ValueError

    ret = []

    for entry in backends:
        ret.append(Backend(entry['host'], entry['port']))

    return ret


class ExproxymentApplication(tornado.web.Application):

    def __init__(self):
        super(ExproxymentApplication, self).__init__([
            (r"/exproxyment/configure", ExproxymentConfigure),
            (r"/exproxyment/register", RegisterSelfHandler),
            (r"/exproxyment/deregister", DeregisterSelfHandler),

            (r"/exproxyment/activity", ExproxymentActivity),

            # reserve the rest of this namespace for ourselves
            (r"/exproxyment.+", FourOhFour),

            (r"/health", MyHealth),
            (r"/health.+", FourOhFour),
            (r"/(.*)", ProxyHandler),
        ])


def main():
    global server_state

    parse_command_line()

    ioloop = tornado.ioloop.IOLoop.instance()

    application = ExproxymentApplication()

    if options.soft_sticky and options.hard_sticky:
        raise Exception("can't be both soft_sticky and hard_sticky")

    if options.backends:
        backends = parse_backends(options.backends)
        backends = [Backend(host['host'], host['port'])
                    for host in backends]
        server_state.set_backends(backends)

    if options.weights:
        weights = parse_weights(options.weights)
        server_state.weights = weights

    HealthDaemon(ioloop).start()
    application.listen(options.port)

    logger.info("Starting on :%d", options.port)
    ioloop.start()


if __name__ == "__main__":
    main()
