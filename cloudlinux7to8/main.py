#!/usr/bin/python3
# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.

import sys

import pleskdistup.main
import pleskdistup.registry

import cloudlinux7to8.upgrader

if __name__ == "__main__":
    pleskdistup.registry.register_upgrader(cloudlinux7to8.upgrader.CloudLinux7to8Factory())
    sys.exit(pleskdistup.main.main())
