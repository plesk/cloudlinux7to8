#!/bin/bash
# Sample script to build cloudlinux7to8 using prebuilt buck

# download the prebuilt buck pex latest version
# wget https://jitpack.io/com/github/facebook/buck/2022.05.05.01/buck-2022.05.05.01.pex -O /root/buck-2022.05.05.01.pex

# make a local build of cloudlinux7to8 via prebuilt buck pex
# assuming the cloudlinux7to8 is cloned in /root/cloudlinux7to8
cd /root/cloudlinux7to8 || exit
/root/buck-2022.05.05.01.pex build :cloudlinux7to8
