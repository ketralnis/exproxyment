Exproxyment is a load balancing proxy that knows about different versions of
backends. It's good at solving the "send 10% of traffic to the new version"
problem

# TODO:

## Production readiness depends on the following items:

* Authentication to API URLs like registering backend and getting status
* Ability to make clients sticky to a version using their IP or a header or a
  combination of both
* Docs. Like this, but better.

## Some nice-to-haves:

* We're likely to use a lot of sockets, so we should check our ulimit when we
  start and assert that we have enough
* Better control over timeouts and connection limits
* Can we avoid having the whole request/response bodies in memory?
* The "test suite" sucks
* Roll the `exproxyment.server` and `exproxyment.config` entrypoints into actual
  scripts that setup.py installs
