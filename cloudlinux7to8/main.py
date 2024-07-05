#!/usr/bin/python3
# Copyright 2024. WebPros International GmbH. All rights reserved.

import sys

import pleskdistup.main
import pleskdistup.registry

import cloudlinux7to8converter.upgrader

if __name__ == "__main__":
    pleskdistup.registry.register_upgrader(cloudlinux7to8converter.upgrader.CloudLinuxConverterFactory())
    sys.exit(pleskdistup.main.main())
