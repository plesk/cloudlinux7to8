# Copyright 2025. WebPros International GmbH. All rights reserved.
from pleskdistup.common import action, leapp_configs, util

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
    def __init__(self):
        self.name = "doing the conversion"

    def _prepare_action(self) -> action.ActionResult:
        try:
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
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 40 * 60
