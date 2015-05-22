#!/usr/bin/env python2.7

import logging
import json

import tornado.ioloop
import tornado.web
from tornado.options import define, options, parse_command_line

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

define('port', default=8080)
define('version', default='1')

class MainHandler(tornado.web.RequestHandler):
    def get(self):
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
