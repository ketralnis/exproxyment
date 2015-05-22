#!/bin/sh

exec ./multiproc.py \
   -- ./simpleserver.py --logging=warn --port=7001 --version=past \
   -- ./simpleserver.py --logging=warn --port=7002 --version=past \
   -- ./simpleserver.py --logging=warn --port=7003 --version=present \
   -- ./simpleserver.py --logging=warn --port=7004 --version=present \
   -- ./simpleserver.py --logging=warn --port=7005 --version=past --insistent \
   \
   -- ./exproxyment.py --logging=warn --port=7000 \
       --backends=localhost:7001,localhost:7002,localhost:7003,localhost:7004,localhost:7005 \
       "$@"
