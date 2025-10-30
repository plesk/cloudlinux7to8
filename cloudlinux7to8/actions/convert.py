# Copyright 2025. WebPros International GmbH. All rights reserved.
import os
from pleskdistup.common import action, leapp_configs, systemd, util

import subprocess
import typing


class LeappPreupgradeRisksPreventedException(Exception):
    def __init__(self, inhibitors: typing.List[str], original_exception: typing.Optional[Exception] = None):
        super().__init__("Leapp preupgrade failed due to preventing factors being found.")
        self.inhibitors = inhibitors
        self.original_exception = original_exception

    def __str__(self):
        inhibitors_str = "\n".join(self.inhibitors)

        original_exception_str = ""
        if self.original_exception is not None:
            original_exception_str = f"Original exception: {self.original_exception}.\n"

        return f"{super().__str__()}\n{original_exception_str}The preventing factors are:\n{inhibitors_str}"


class DoCloudLinux7to8Convert(action.ActiveAction):
    LEAPP_RESUME_SERVICE = "leapp_resume.service"

    def __init__(self):
        self.name = "doing the conversion"

    def _prepare_action(self) -> action.ActionResult:
        try:
            util.logged_check_call(["/usr/bin/dnf", "clean", "all"])
            util.logged_check_call(["/usr/bin/leapp", "preupgrade"])
        except subprocess.CalledProcessError as e:
            inhibitors = leapp_configs.extract_leapp_report_inhibitors()
            if inhibitors:
                raise LeappPreupgradeRisksPreventedException(inhibitors, e)
            else:
                raise e

        util.logged_check_call(["/usr/bin/leapp", "upgrade", "--nowarn"])
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        leapp_py3_utility = "/root/tmp_leapp_py3/leapp3"

        # We don't want LEAPP_RESUME_SERVICE will be started in the middle of finishing stage because it
        # could break our normal flow. So we need to prevent systemd from starting it and call directly
        if systemd.is_service_exists(self.LEAPP_RESUME_SERVICE):
            systemd.disable_services([self.LEAPP_RESUME_SERVICE])
            if os.path.exists(leapp_py3_utility):
                util.logged_check_call([leapp_py3_utility, "upgrade", "--resume"])
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 40 * 60
