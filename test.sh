#!/bin/sh

# This is the exproxyment "test suite". It's not very good, and it badly needs
# replacement with real tests. Its only real goal is to exercise every line of
# code, not verify actual correctness. To use:
# 1. In one window, launch test.sh
# 2. In another window, launch test2.sh
# 3. Watch for exceptions in either window

set -e

export PYTHONPATH=.
export LOGLEVEL=warn

python -m exproxyment.multiproc \
    -- python -m exproxyment.server --logging=$LOGLEVEL --port=7000 \
      --backends=localhost:7001,localhost:7002,localhost:7003,localhost:7004,localhost:7005,localhost:7006,localhost:7007 \
      --weights=past:1,present:2 \
      "$@" \
    -- python -m exproxyment.simpleserver --logging=$LOGLEVEL --port=7001 --version=past \
    -- python -m exproxyment.simpleserver --logging=$LOGLEVEL --port=7002 --version=past \
    -- python -m exproxyment.simpleserver --logging=$LOGLEVEL --port=7003 --version=present \
    -- python -m exproxyment.simpleserver --logging=$LOGLEVEL --port=7004 --version=present \
    -- python -m exproxyment.simpleserver --logging=$LOGLEVEL --port=7005 --version=past --insistent \
    -- python -m exproxyment.simpleserver --logging=$LOGLEVEL --port=7006 --version=future \
    -- python -m exproxyment.simpleserver --logging=$LOGLEVEL --port=7008 --version=past --register_from=localhost:7008 --register_to=localhost:7000 \
    -- python -m exproxyment.simpleserver --logging=$LOGLEVEL --port=7009 --version=future --register_from=localhost:7009 --register_to=localhost:7000 \
