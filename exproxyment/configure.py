#!/usr/bin/env python2.7

import json

from tornado.options import define, options, parse_command_line
import tornado.httpclient

define('backends', default='')
define('show_backends', default=False, type=bool)
define('weights', default='')
define('show_weights', default=False, type=bool)
define('server', default='localhost:7000')
define('show_health', default=False, type=bool)

def configure(path, js=None):
    print path, '->', js if js else ''
    client = tornado.httpclient.HTTPClient()
    response = client.fetch("http://%s%s" % (options.server, path),
                            method='POST' if js else 'GET',
                            body=json.dumps(js) if js else None)

    if response.code != 200:
        raise Exception("Code(%d): %s" % (response.code, response.body))

    print response.body.strip()

    return json.loads(response.body)

def main():
    parse_command_line()

    if options.backends:
        backends = options.backends.split(',')
        backends = map(lambda s: s.split(':'), backends)
        backends = [{'host': host, 'port': int(port)}
                    for (host, port)
                    in backends]
        configure('/exproxyment/backends', {'backends': backends})

    if options.weights:
        weights = options.weights.split(',')
        weights = map(lambda s: s.split(':'), weights)
        weights = {version: int(weight)
                   for (version, weight)
                   in weights}
        configure('/exproxyment/weights', {'weights': weights})

    if options.show_backends:
        configure('/exproxyment/backends')

    if options.show_weights:
        configure('/exproxyment/weights')

    if options.show_health:
        configure('/health')


if __name__ == "__main__":
    main()
