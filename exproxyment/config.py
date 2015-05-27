#!/usr/bin/env python2.7

import json

from tornado.options import define, options, parse_command_line
import tornado.httpclient

from .utils import parse_backends, parse_weights
from .utils import unparse_backends, unparse_weights

define('backends', default='')
define('show_backends', default=False, type=bool)
define('weights', default='')
define('show_weights', default=False, type=bool)
define('server', default='localhost:7000')
define('show_health', default=False, type=bool)
define('json', type=bool, default=False)

def configure(path, js=None):
    client = tornado.httpclient.HTTPClient()
    response = client.fetch("http://%s%s" % (options.server, path),
                            method='POST' if js else 'GET',
                            body=json.dumps(js) if js else None)

    if response.code != 200:
        raise Exception("Code(%d): %s" % (response.code, response.body))

    return json.loads(response.body)

def main():
    parse_command_line()

    if options.backends:
        backends = parse_backends(options.backends)
        configure('/exproxyment/backends', {'backends': backends})

    if options.weights:
        weights = parse_weights(options.weights)
        configure('/exproxyment/weights', {'weights': weights})

    if options.show_backends:
        ret = configure('/exproxyment/backends')
        if options.json:
            print json.dumps(ret)
        else:
            print unparse_backends(ret['backends'])

    if options.show_weights:
        ret = configure('/exproxyment/weights')
        if options.json:
            print json.dumps(ret)
        else:
            print unparse_weights(ret['weights'])

    if options.show_health:
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
