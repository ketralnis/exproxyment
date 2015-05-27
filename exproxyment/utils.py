def parse_backends(b_str):
    backends = b_str.split(',')
    backends = map(lambda s: s.split(':'), backends)
    backends = [{'host': host, 'port': int(port)}
                for (host, port)
                in backends]
    return backends

def unparse_backends(b_json):
    return ','.join('%s:%d' % (b['host'], b['port'])
                    for b in b_json)

def parse_weights(w_str):
    weights = w_str.split(',')
    weights = map(lambda s: s.split(':'), weights)
    weights = {version: int(weight)
               for (version, weight)
               in weights}
    return weights

def unparse_weights(w_json):
    return ','.join('%s:%d' % (version, weight)
                    for version, weight
                    in w_json.items())
