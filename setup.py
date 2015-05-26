#!/usr/bin/env python

from setuptools import find_packages
from distutils.core import setup

setup(
    name='exproxyment',
    version="",
    packages=find_packages(),
    install_requires=[
        "tornado>=4.0.0",
    ])
