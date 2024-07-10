# Copyright 2024. WebPros International GmbH. All rights reserved.
import os
import shutil
import subprocess
import typing

from pleskdistup.common import action, files, log, motd, rpm, util


class FixNamedConfig(action.ActiveAction):
    user_options_path: str
    chrooted_file_path: str

    def __init__(self) -> None:
        self.name = "fix named configuration"
        self.user_options_path = "/etc/named-user-options.conf"
        self.chrooted_file_path = "/var/named/chroot/etc/named-user-options.conf"

    def _is_required(self) -> bool:
        return os.path.exists(self.chrooted_file_path)

    def _prepare_action(self) -> action.ActionResult:
        if not os.path.exists(self.user_options_path):
            os.symlink(self.chrooted_file_path, self.user_options_path)

        if os.path.getsize(self.chrooted_file_path) == 0:
            with open(self.chrooted_file_path, "w") as f:
                # Leapp fails if the file is empty, so write a dummy comment
                f.write("# cloudlinux7to8 workaround commentary")

        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        if os.path.exists(self.user_options_path):
            os.unlink(self.user_options_path)

        with open(self.chrooted_file_path, "r") as f:
            if f.read() == "# cloudlinux7to8 workaround commentary":
                os.unlink(self.chrooted_file_path)
                with open(self.chrooted_file_path, "w") as _:
                    pass

        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        if os.path.exists(self.user_options_path):
            os.unlink(self.user_options_path)

        return action.ActionResult()


class DisableSuspiciousKernelModules(action.ActiveAction):
    suspicious_modules: typing.Set[str]
    modules_config_path: str

    def __init__(self) -> None:
        self.name = "disable suspicious kernel modules"
        self.suspicious_modules = {"pata_acpi", "btrfs", "floppy"}
        self.modules_config_path = "/etc/modprobe.d/pataacpibl.conf"

    def _get_enabled_modules(self, lookup_modules: typing.Set[str]) -> typing.Set[str]:
        modules = set()
        modules_list = subprocess.check_output(["/usr/sbin/lsmod"], universal_newlines=True).splitlines()
        for line in modules_list:
            module_name = line[:line.find(' ')]
            if module_name in lookup_modules:
                modules.add(module_name)
        return modules

    def _prepare_action(self) -> action.ActionResult:
        with open(self.modules_config_path, "a") as kern_mods_config:
            for suspicious_module in self.suspicious_modules:
                kern_mods_config.write(f"blacklist {suspicious_module}\n")

        for enabled_modules in self._get_enabled_modules(self.suspicious_modules):
            util.logged_check_call(["/usr/sbin/rmmod", enabled_modules])

        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        for module in self.suspicious_modules:
            files.replace_string(self.modules_config_path, "blacklist " + module, "")

        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        if not os.path.exists(self.modules_config_path):
            return action.ActionResult()

        for module in self.suspicious_modules:
            files.replace_string(self.modules_config_path, "blacklist " + module, "")

        return action.ActionResult()


class FixSyslogLogrotateConfig(action.ActiveAction):
    config_path: str
    path_to_backup: str
    right_logrotate_config: str

    def __init__(self, store_dir: str) -> None:
        self.name = "fix logrotate config for rsyslog"
        self.config_path = "/etc/logrotate.d/syslog"
        self.path_to_backup = store_dir + "/syslog.logrotate.bak"
        self.right_logrotate_config = """
/var/log/cron
/var/log/messages
/var/log/secure
/var/log/spooler
{
    missingok
    sharedscripts
    postrotate
        /usr/bin/systemctl kill -s HUP rsyslog.service >/dev/null 2>&1 || true
    endscript
}
"""

    def _prepare_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        shutil.move(self.config_path, self.path_to_backup)

        with open(self.config_path, "w") as f:
            f.write(self.right_logrotate_config)

        # File installed from the package isn't suitable for our goals, because
        # it will rotate /var/log/maillog, which should be processed from Plesk side
        rpmnew_file = self.config_path + ".rpmnew"
        if os.path.exists(rpmnew_file):
            os.remove(rpmnew_file)

        motd.add_finish_ssh_login_message(f"The logrotate configuration for rsyslog has been updated. The old configuration has been saved as {self.path_to_backup}\n")
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()


class RecreateAwstatsConfigurationFiles(action.ActiveAction):
    def __init__(self) -> None:
        self.name = "recreate AWStats configuration files for domains"

    def get_awstats_domains(self) -> typing.Set[str]:
        domains_awstats_directory = "/usr/local/psa/etc/awstats/"
        domains = set()
        for awstats_config_file in os.listdir(domains_awstats_directory):
            if awstats_config_file.startswith("awstats.") and awstats_config_file.endswith("-http.conf"):
                domains.add(awstats_config_file.split("awstats.")[-1].rsplit("-http.conf")[0])
        return domains

    def _prepare_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        rpm.handle_all_rpmnew_files("/etc/awstats")

        for domain in self.get_awstats_domains():
            log.info(f"Recreating AWStats configuration for domain: {domain}")
            util.logged_check_call(
                [
                    "/usr/sbin/plesk", "sbin", "webstatmng", "--set-configs",
                    "--stat-prog", "awstats", "--domain-name", domain
                ], stdin=subprocess.DEVNULL
            )
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()

    def estimate_post_time(self) -> int:
        # Estimate 100 ms per configuration we have to recreate
        return int(len(self.get_awstats_domains()) / 10) + 5
