#!/usr/bin/env python2.7

import sys
import json
import logging

from tornado.options import define, options, parse_command_line
import tornado.httpclient

from .utils import parse_backends, parse_weights
from .utils import unparse_backends, unparse_weights

define('backends', default='')
define('show', default=False, type=bool)
define('add', default=None, type=str)
define('remove', default=None, type=str)
define('weights', default='')
define('server', default='localhost:7000')
define('health', default=False, type=bool)
define('activity', default=False, type=bool)
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
    exit_status = 0

    parse_command_line()

    if options.backends or options.weights:
        config = {}

        if options.backends:
            config['backends'] = parse_backends(options.backends)

        if options.weights:
            config['weights'] = parse_weights(options.weights)

        configure('/exproxyment/configure', config)

    if options.add:
        config = {'backends': parse_backends(options.add)}
        configure('/exproxyment/register', config)

    if options.remove:
        config = {'backends': parse_backends(options.remove)}
        configure('/exproxyment/deregister', config)

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

        if not ret['healthy']:
            # TODO right now configure() will bail with an exception before we
            # get here
            exit_status = 1

    if options.activity:
        ret = configure('/exproxyment/activity')
        if options.json:
            print json.dumps(ret)
        else:
            for activity in ret['activity']:
                backend = activity['backend']
                print '%s -> %s:%d %s' % (
                    activity['source_host'],
                    backend['host'], backend['port'],
                    activity['uri'],
                )

    sys.exit(exit_status)


if __name__ == "__main__":
    main()
