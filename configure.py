#!/usr/bin/env python2.7

import json

from tornado.options import define, options, parse_command_line
import tornado.httpclient

define('backends', default='')
define('list_backends', default='')
define('weights', default='')
define('list_weights', default='')
define('server', default='localhost:7000')

def configure(path, js=None):
    print path, '->', js if js else ''
    client = tornado.httpclient.HTTPClient()
    response = client.fetch("http://%s%s" % (options.server, path),
                            method='POST' if js else 'GET',
                            body=json.dumps(js) if js else None)

    if response.code != 200:
        raise Exception("Code(%d): %s" % (response.code, response.body))

    print response.body

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

    if options.list_backends:
        configure('/exproxyment/backends')

    if options.list_weights:
        configure('/exproxyment/weights')


if __name__ == "__main__":
    main()
