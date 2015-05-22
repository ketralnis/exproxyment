#!/usr/bin/env python2.7

from collections import namedtuple
import logging
from functools import partial
import random
import json
import urllib
from copy import deepcopy

import tornado.ioloop
import tornado.web
import tornado.gen
import tornado.httpclient
from tornado.ioloop import PeriodicCallback
from tornado.options import define, options, parse_command_line

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

define('port', type=int, default=8080)
define('backends', default='')
define('cookie_domain', default='localhost:8080')
define('weights', default='')
define('soft_sticky', type=bool, default=True)
define('hard_sticky', type=bool, default=False)

BackendState = namedtuple('BackendState', 'healthy version')
Backend = namedtuple('Backend', 'host port')


class ServerState(object):

    def __init__(self, backends=None, weights=None):
        self.backends = backends or {}
        self.weights = weights or {}

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


# TODO need this global state to live somewhere. it's set in main()
server_state = ServerState()


class HealthDeamon(object):

    def __init__(self, ioloop, periodicity=1000):
        self.ioloop = ioloop
        self.periodic = PeriodicCallback(self.task, periodicity, self.ioloop)

    def start(self):
        self.periodic.start()

    @tornado.gen.coroutine
    def task(self):
        # do health checks
        backend, state = random.choice(server_state.backends.items())
        logger.info("Health checking %r (healthy was %r, version was %r)",
                    backend, state.healthy, state.version)
        client = tornado.httpclient.AsyncHTTPClient()
        url = 'http://%s:%d/health' % (backend.host, backend.port)

        try:
            response = yield client.fetch(url,
                                          connect_timeout=500,
                                          request_timeout=500)
        except Exception as ex:
            code = 599
        else:
            code = response.code

        if code not in (200, 599):
            logger.info("%r responded with code:%d", backend, code)
        else:
            logger.debug("%r responded with code:%d", backend, code)

        if code != 200:

            server_state.backends[backend] = BackendState(healthy=False,
                                                          version=None)
            return

        body = json.loads(response.body)
        healthy = body.get('healthy', False)
        version = body.get('version', None)
        if healthy is not True or not version:
            logger.info("Unhealthy %r (%r:%r)", backend, healthy, version)
            server_state.backends[backend] = BackendState(healthy=False,
                                                          version=None)
            return

        logger.info("Healthy %r (%r:%r)", backend, healthy, version)
        server_state.backends[backend] = BackendState(healthy=True,
                                                      version=version)


class BaseHandler(tornado.web.RequestHandler):

    def write_json(self, js):
        self.write(json.dumps(js))
        self.write('\n')

    def nope(self, reason, code=504):
        self.set_status(code)
        self.write(reason)
        self.write('\n')


class ProxyHandler(BaseHandler):

    def requested_version(self):
        """
        Determine what version the user has requested and how strongly they feel
        about it

        returns a tuple of (Required, Version)
        """

        ## header

        required_version = self.request.headers.get('X-Exproxyment-Require-Version',
                                                    None)
        if required_version:
            return True, required_version

        requested_version = self.request.headers.get('X-Exproxyment-Request-Version',
                                                     None)
        if requested_version:
            return False, required_version

        ## cookie

        required_version = self.request.cookies.get('exproxyment_require_version',
                                                    None)
        if requested_version:
            return False, required_version

        requested_version = self.request.cookies.get('exproxyment_request_version',
                                                     None)
        if requested_version:
            return False, required_version

        ## get param

        required_version = self.get_argument('exproxyment_require_version',
                                             None)
        if requested_version:
            return False, required_version

        requested_version = self.get_argument('exproxyment_request_version',
                                              None)
        if requested_version:
            return False, requested_version
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

        # otherwise take the weights the administator gave us. TODO do a proper
        # random weighting, and try to find a way to make these stickier than
        # just cookies. also ketama instead of this nonsense
        choices = []
        for version in available_versions:
            choices.extend([version]*server_state.weights.get(version, 0))

        if choices:
            return random.choice(choices)

        return None


    @tornado.gen.coroutine
    def proxy(self, path):
        client = tornado.httpclient.AsyncHTTPClient()

        required, version = self.requested_version()

        if not server_state.healthy():
            self.nope('no backends available')
            return

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
        url = 'http://%s:%d/%s' % (backend.host, backend.port, path)
        method = self.request.method
        headers = deepcopy(self.request.headers)

        headers.add('X-Exproxyment-Version', version)

        body = None
        if method != 'GET':
            body = self.request.body

        try:
            response = yield client.fetch(url,
                                          method=method,
                                          body=body)
        except Exception as e:
            self.nope("bad connection to %r (%r)" % (backend, e))
            return

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
            cookie_value = urllib.quote(version)

            self.add_header('Set-Cookie',
                            '%s=%s' % (cookie_name, cookie_value))

        self.write(response.body)

    get = proxy
    post = proxy
    head = proxy
    put = proxy
    delete = proxy


class MyHealth(BaseHandler):

    def get(self):
        for_version = self.get_argument('for_version', None)

        healthy = server_state.healthy(for_version)

        if not healthy:
            self.set_status(500)

        ret = {
            'healthy': healthy,
            'versions': list(server_state.available_versions()),
            'weights': server_state.weights,
            'backends': [{'host': backend.host,
                          'port': backend.port,
                          'healthy': state.healthy,
                          'version': state.version}
                         for (backend, state)
                         in server_state.backends.iteritems()],
        }

        self.write(json.dumps(ret))
        self.write('\n') # makes debugging easier to read


class ExproxymentBackends(BaseHandler):

    def get(self):
        self.write_json({'backends': [{'host': backend.host,
                                       'port': backend.port,
                                       'healthy': state.healthy,
                                       'version': state.version}
                                      for (backend, state)
                                      in server_state.backends.iteritems()]})

    def post(self):
        body = json.loads(self.request.body)
        body = body['backends']

        # validate the format of the servers
        if not (isinstance(body, list)
                and (isinstance(k, basestring)
                     and isinstance(v, basestring)
                     for (k, v)
                     in body)):
            self.set_status('400')
            self.write(json.dumps({'error': 'bad format'}))
            return

        new_backends = {}

        for entry in body:
            backend = Backend(entry['host'], entry['port'])
            # make sure the inherit the previous state if we already knew about
            # this server, otherwise this will wipe out all of the servers we
            # know about and we'll start returning 504s
            state = server_state.backends.get(backend, BackendState(False, None))
            new_backends[backend] = state

        # swap them in
        server_state.backends = new_backends

        # validate the format of the new weights
        self.write_json({'status': 'ok'})


class ExproxymentWeights(BaseHandler):

    def get(self):
        self.write_json({'weights': server_state.weights})

    def post(self):
        body = json.loads(self.request.body)
        body = body['weights']

        # validate the format of the new weights
        if not (isinstance(body, dict)
                and (isinstance(k, basestring)
                     and isinstance(v, (int, long))
                     for (k, v) in body.items())):
            self.set_status(400)
            self.write_json({'error': 'bad format'})
            return

        server_state.weights = body

        self.write_json({'status': 'ok', 'weights': body})


def main():
    global server_state

    parse_command_line()

    application = tornado.web.Application([
        (r"/exproxyment/backends", ExproxymentBackends),
        (r"/exproxyment/weights", ExproxymentWeights),
        (r"/health", MyHealth),
        (r"/(.*)", ProxyHandler),
    ])

    ioloop = tornado.ioloop.IOLoop.instance()

    HealthDeamon(ioloop).start()
    application.listen(options.port)

    if not options.backends:
        raise Exception("--servers is mandatory")

    if options.soft_sticky and options.hard_sticky:
        raise Exception("can't be both soft_sticky and hard_sticky")

    servers = options.backends.split(',')
    servers = [server.split(':') for server in servers]
    servers = {Backend(host, int(port)): BackendState(healthy=None,
                                                      version=None)
               for (host, port) in servers}
    server_state.backends = servers

    weights = None
    if options.weights:
        buckets = options.weights.split(',')
        buckets = [entry.split(':') for entry in buckets]
        buckets = {version: int(weight) for (version, weight) in buckets}
        server_state.weights = buckets

    logger.info("Starting %r on :%d", __file__, options.port)
    ioloop.start()


if __name__ == "__main__":
    main()
