def parse_backends(b_str):
    backends = b_str.split(',')
    backends = map(lambda s: s.split(':'), backends)
    backends = [{'host': host, 'port': int(port)}
                for (host, port)
                in backends]
    return backends

def parse_weights(w_str):
    weights = w_str.split(',')
    weights = map(lambda s: s.split(':'), weights)
    weights = {version: int(weight)
               for (version, weight)
               in weights}
    return weights
