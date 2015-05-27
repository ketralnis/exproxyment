#!/bin/sh

export PYTHONPATH=.
export LOGLEVEL=warn

python -m exproxyment.multiproc \
   -- python -m exproxyment.simpleserver --logging=$LOGLEVEL --port=7001 --version=past \
   -- python -m exproxyment.simpleserver --logging=$LOGLEVEL --port=7002 --version=past \
   -- python -m exproxyment.simpleserver --logging=$LOGLEVEL --port=7003 --version=present \
   -- python -m exproxyment.simpleserver --logging=$LOGLEVEL --port=7004 --version=present \
   -- python -m exproxyment.simpleserver --logging=$LOGLEVEL --port=7005 --version=past --insistent \
   -- python -m exproxyment.simpleserver --logging=$LOGLEVEL --port=7006 --version=future \
   -- python -m exproxyment.server --logging=$LOGLEVEL --port=7000 \
       --backends=localhost:7001,localhost:7002,localhost:7003,localhost:7004,localhost:7005,localhost:7006,localhost:7007 \
       --weights=past:1,present:2 \
       "$@"

