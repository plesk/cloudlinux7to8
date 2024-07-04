# Copyright 1999 - 2024. Plesk International GmbH. All rights reserved.
import os
import shutil

from pleskdistup.common import action, rpm, util

LEAPP_CLOUDLINUX_RPM_URL = "https://repo.cloudlinux.com/elevate/elevate-release-latest-el7.noarch.rpm"


class LeapInstallation(action.ActiveAction):

    def __init__(self, elevate_release_rpm_url, pkgs_to_install):
        self.name = "installing leapp"
        self.pkgs_to_install = pkgs_to_install
        self.elevate_release_rpm_url = elevate_release_rpm_url

    def _prepare_action(self) -> action.ActionResult:
        if not rpm.is_package_installed("elevate-release"):
            util.logged_check_call(["/usr/bin/yum", "install", "-y", self.elevate_release_rpm_url])

        util.logged_check_call(["/usr/bin/yum-config-manager", "--enable", "elevate"])

        util.logged_check_call(["/usr/bin/yum", "install", "-y"] + self.pkgs_to_install)
        # We want to prevent the leapp packages from being updated accidentally to
        # the latest version (for example by using 'yum update -y'). Therefore, we
        # should disable the 'elevate' repository. Additionally, this will prevent
        # the pre-checker from detecting leapp as outdated and prevent re-evaluation
        # on the next restart.
        util.logged_check_call(["/usr/bin/yum-config-manager", "--disable", "elevate"])
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        rpm.remove_packages(
            rpm.filter_installed_packages(
                self.pkgs_to_install + ["elevate-release", "leapp-upgrade-el7toel8"]
            )
        )

        leapp_related_files = [
            "/root/tmp_leapp_py3/leapp",
        ]
        for file in leapp_related_files:
            if os.path.exists(file):
                os.unlink(file)

        leapp_related_directories = [
            "/etc/leapp",
            "/var/lib/leapp",
            "/var/log/leapp",
            "/usr/lib/python2.7/site-packages/leapp",
        ]
        for directory in leapp_related_directories:
            if os.path.exists(directory):
                shutil.rmtree(directory)

        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 40
