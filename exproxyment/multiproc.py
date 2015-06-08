#!/usr/bin/env python

import os
import sys
import signal
import logging


def multijob(jobs):
    pids = {}

    for job in jobs:
        logging.debug('starting %r', job)
        pid = os.spawnvp(os.P_NOWAIT, job[0], job)
        pids[pid] = job

    if not pids:
        return

    diedfirst = None

    logging.debug('finished starting %d jobs', len(pids))

    try:
        diedfirst, retcode = os.wait()
        logging.info('died: %r with %r', pids[diedfirst], retcode)
    except KeyboardInterrupt:
        pass

    if diedfirst:
        del pids[diedfirst]

    for pid, job in pids.items():
        logging.info('killing %r', job)
        os.kill(pid, signal.SIGINT)

    while pids:
        logging.debug('waiting on %r more jobs: %r',
                      len(pids), [j[0] for j in pids.values()])
        died, retcode = os.wait()
        logging.debug('received %r from %r', retcode, pids[died])
        del pids[died]


def splitlist(l, sep):
    ret = [[]]
    for x in l:
        if x == sep:
            ret.append([])
        else:
            ret[-1].append(x)

    # let them start or end the commandline with the separator
    if not ret[0]:
        ret = ret[1:]
    if not ret[-1]:
        ret = ret[:-1]

    return ret

jobs = splitlist(sys.argv[1:], '--')
multijob(jobs)
