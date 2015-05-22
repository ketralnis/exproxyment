#!/bin/sh

exec ./multiproc.py \
    -- ./exproxyment.py --port=7000 \
        --backends=localhost:7001,localhost:7002,localhost:7003,localhost:7004 \
        "$@" \
   -- ./simpleserver.py --port=7001 --version=past \
   -- ./simpleserver.py --port=7002 --version=past \
   -- ./simpleserver.py --port=7003 --version=present \
   -- ./simpleserver.py --port=7004 --version=present