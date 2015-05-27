#!/usr/bin/env python2.7

import json
import logging

from tornado.options import define, options, parse_command_line
import tornado.httpclient

from .utils import parse_backends, parse_weights
from .utils import unparse_backends, unparse_weights

define('backends', default='')
define('show', default=False, type=bool)
define('weights', default='')
define('server', default='localhost:7000')
define('health', default=False, type=bool)
define('json', type=bool, default=False)

def configure(path, js=None):
    client = tornado.httpclient.HTTPClient()
    url = "http://%s%s" % (options.server, path)
    method = 'POST' if js else 'GET'

    logging.debug("%s %s", method, url)

    response = client.fetch(url,
                            method=method,
                            body=json.dumps(js) if js else None)

    logging.debug("%s %s (%d):\n%s", method, url, response.code,
                  response.body and response.body.strip())

    if response.code != 200:
        raise Exception("%s %s code(%d): %s"
                        % (method, url, response.code, response.body))

    return json.loads(response.body)

def main():
    parse_command_line()

    if options.backends or options.weights:
        config = {}

        if options.backends:
            config['backends'] = parse_backends(options.backends)

        if options.weights:
            config['weights'] = parse_weights(options.weights)

        configure('/exproxyment/configure', config)

    if options.show:
        ret = configure('/exproxyment/configure')

        if options.json:
            print json.dumps(ret)
        else:
            print 'backends:', unparse_backends(ret['backends'])
            print 'weights:', unparse_weights(ret['weights'])

    if options.health:
        ret = configure('/health')
        if options.json:
            print json.dumps(ret)
        else:
            for backend in ret['backends']:
                print '%s:%d(%s): %s' % (
                    backend['host'], backend['port'],
                    backend['version'] or 'unknown',
                    'healthy' if backend['healthy'] else 'unhealthy',
                )


if __name__ == "__main__":
    main()
