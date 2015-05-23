#!/usr/bin/env python2.7

import logging
import json

import tornado.ioloop
import tornado.web
from tornado.options import define, options, parse_command_line

logger = logging.getLogger(__name__)

define('port', default=8080)
define('version', default='1')
define('insistent', type=bool, default=False)

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
    ioloop.start()


if __name__ == "__main__":
    main()
