#!/bin/sh

export PYTHONPATH=.

python -m exproxyment.multiproc \
   -- python -m exproxyment.simpleserver --logging=warn --port=7001 --version=past \
   -- python -m exproxyment.simpleserver --logging=warn --port=7002 --version=past \
   -- python -m exproxyment.simpleserver --logging=warn --port=7003 --version=present \
   -- python -m exproxyment.simpleserver --logging=warn --port=7004 --version=present \
   -- python -m exproxyment.simpleserver --logging=warn --port=7005 --version=past --insistent \
   -- python -m exproxyment.exproxyment --logging=warn --port=7000 \
       --backends=localhost:7001,localhost:7002,localhost:7003,localhost:7004,localhost:7005 \
       "$@"
