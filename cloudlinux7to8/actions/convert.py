# Copyright 2025. WebPros International GmbH. All rights reserved.
from pleskdistup.common import action, util


class DoCloudLinux7to8Convert(action.ActiveAction):
    def __init__(self):
        self.name = "doing the conversion"

    def _prepare_action(self) -> action.ActionResult:
        util.logged_check_call(["/usr/bin/leapp", "preupgrade"])
        util.logged_check_call(["/usr/bin/leapp", "upgrade", "--nowarn"])
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 40 * 60
