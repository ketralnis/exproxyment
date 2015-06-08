#!/bin/sh

set -e
set -v

# test.sh sets us up with servers this way:
# 7001: past
# 7002: past
# 7003: present
# 7004: present
# 7005: past (insistent)
# 7006: future
# 7007: (no server)
# 7008: past --register_from=localhost:7008 --register_to=localhost:7000 \
# 7009: future --register_from=localhost:7009 --register_to=localhost:7000 \

# test that --server works so we can use the default from now on
python -m exproxyment.config --server=$(hostname):7000 --health
! python -m exproxyment.config --server=$(hostname):7999 --health >/dev/null 2>&1

# there's no server here so this should register unhealthiness
python -m exproxyment.config --backends=localhost:7007
! python -m exproxyment.config --health

# set the default configs
python -m exproxyment.config --backends=localhost:7001,localhost:7002,localhost:7003,localhost:7004,localhost:7005,localhost:7006,localhost:7007
python -m exproxyment.config --weights=past:1,present:2

python -m exproxyment.config --show
python -m exproxyment.config --show --json

# let it check on some new servers that we just added
sleep 1

python -m exproxyment.config --health
python -m exproxyment.config --health --json

# make sure at least one is up so we don't fail later on
curl http://localhost:7001/health

# basic operation
curl http://localhost:7000 | grep version

# test activity
curl http://localhost:7000/slow &
python -m exproxyment.config --activity | grep 127
python -m exproxyment.config --activity --json | grep 127
wait

# make sure we only get the configured versions
curl -v http://localhost:7000 2>&1 | grep -E 'X-Exproxyment-Version: (past|present)'
! curl -v http://localhost:7000 2>&1 | grep -E 'X-Exproxyment-Version: future'

# GET arg version requesting
curl -v http://localhost:7000?exproxyment_request_version=past 2>&1 | grep -E 'X-Exproxyment-Version: past'
curl -v http://localhost:7000?exproxyment_request_version=present 2>&1 | grep -E 'X-Exproxyment-Version: present'
curl -v http://localhost:7000?exproxyment_request_version=future 2>&1 | grep -E 'X-Exproxyment-Version: future'
curl -v http://localhost:7000?exproxyment_require_version=future 2>&1 | grep -E 'X-Exproxyment-Version: future'
curl -v http://localhost:7000?exproxyment_request_version=never 2>&1 | grep -E 'X-Exproxyment-Version: (past|present)'
curl -v http://localhost:7000?exproxyment_require_version=never 2>&1 | grep -E 'no backend available for never'

# header version requesting
curl -v http://localhost:7000 -H 'X-Exproxyment-Request-Version: past' 2>&1 | grep -E 'X-Exproxyment-Version: past'
curl -v http://localhost:7000 -H 'X-Exproxyment-Request-Version: present' 2>&1 | grep -E 'X-Exproxyment-Version: present'
curl -v http://localhost:7000 -H 'X-Exproxyment-Request-Version: future' 2>&1 | grep -E 'X-Exproxyment-Version: future'
curl -v http://localhost:7000 -H 'X-Exproxyment-Request-Version: never' 2>&1 | grep -E 'X-Exproxyment-Version: (past|present)'

# cookie version requesting
curl -v http://localhost:7000 -b 'exproxyment_request_version='%7B%22version%22%3A%20%22past%22%7D'' 2>&1 | grep -E 'X-Exproxyment-Version: past'
curl -v http://localhost:7000 -b 'exproxyment_request_version='%7B%22version%22%3A%20%22present%22%7D'' 2>&1 | grep -E 'X-Exproxyment-Version: present'
curl -v http://localhost:7000 -b 'exproxyment_request_version='%7B%22version%22%3A%20%22future%22%7D'' 2>&1 | grep -E 'X-Exproxyment-Version: future'
curl -v http://localhost:7000 -b 'exproxyment_request_version='%7B%22version%22%3A%20%22never%22%7D'' 2>&1 | grep -E 'X-Exproxyment-Version: (past|present)'

# cookie round trip
rm -fv cookie.jar
v=$(curl -v -c cookie.jar http://localhost:7000 2>&1 | awk '/X-Exproxyment-Version/ {print $3}')
echo "Selected version: " $v
# make sure we get the same version
curl -v -c cookie.jar http://localhost:7000 2>&1 | grep "$v"

echo 'success!'
