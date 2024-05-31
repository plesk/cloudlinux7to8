#!/bin/bash
# Sample script to build centos2alma using prebuilt buck

# download the prebuilt buck pex latest version
# wget https://jitpack.io/com/github/facebook/buck/2022.05.05.01/buck-2022.05.05.01.pex -O /root/buck-2022.05.05.01.pex

# make a local build of centos2alma via prebuilt buck pex
# assuming the centos2alma is cloned in /root/centos2alma
cd /root/centos2alma || exit
/root/buck-2022.05.05.01.pex build :centos2alma
