#!/usr/bin/env python2.7

import sys
import logging
import json

import tornado.ioloop
import tornado.httpclient
import tornado.web
import tornado.gen
from tornado.options import define, options, parse_command_line

logger = logging.getLogger(__name__)

define('port', default=8080)
define('version', default='1')
define('insistent', type=bool, default=False)

define('register_from', type=str, default=None)
define('register_to', type=str, default=None)


class MainHandler(tornado.web.RequestHandler):

    def get(self):
        requested_version = self.request.headers.get('X-Exproxyment-Version')

        if (options.insistent
                and requested_version != options.version):
            # they gave us the wrong version, tell them to try again
            self.set_status(406)
            self.set_header('X-Exproxyment-Wrong-Version', 'true')
            logging.warn("Got version %r but wanted %r",
                         self.request.headers.get('X-Exproxyment-Version'),
                         options.version)
            return

        self.write(json.dumps({
            'port': options.port,
            'version': options.version,
        }))
        self.write('\n')


class HealthHandler(tornado.web.RequestHandler):

    def get(self):
        self.write(json.dumps({
            'healthy': True,
            'version': options.version,
        }))
        self.write('\n')


def split_host(s):
    host, port = s.split(':')
    port = int(port)
    return host, port


def die(message):
    logging.error("Dying: %r", message)
    sys.exit(1)


@tornado.gen.coroutine
def register_self():
    try:
        # wait a sec for the server to come up
        yield tornado.gen.sleep(1)

        yield _register_self()
    except Exception as e:
        # if we fail to register ourselves, we want to kill the server
        die(repr(e))


@tornado.gen.coroutine
def _register_self():
    fromhost, fromport = split_host(options.register_from)
    tohost, toport = split_host(options.register_to)

    url = 'http://%s:%d/exproxyment/register' % (tohost, toport)
    body = json.dumps({'backends': [
                        {'host': fromhost, 'port': fromport}]})
    headers = {'Content-Type': 'application/json'}

    client = tornado.httpclient.AsyncHTTPClient()
    request = tornado.httpclient.HTTPRequest(url, method='POST',
                                             headers=headers,
                                             body=body)
    response = yield client.fetch(request)
    if response.code != 200:
        die("Got code %d on on register (%s)"
            % (response.code, response.body))


def main():
    parse_command_line()

    application = tornado.web.Application([
        (r"/", MainHandler),
        (r"/health", HealthHandler),
    ])

    ioloop = tornado.ioloop.IOLoop.instance()
    application.listen(options.port)

    logger.debug("Starting %r on port:%d version:%r",
                 __file__,
                 options.port, options.version)

    if options.register_from or options.register_to:
        if not options.register_from and options.register_to:
            raise Exception(
                'If you specify --register_from or --register_to you have to specify both')

        ioloop.spawn_callback(register_self)

    ioloop.start()


if __name__ == "__main__":
    main()
