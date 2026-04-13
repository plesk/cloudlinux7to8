# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.
import os
import shutil
import subprocess
import typing

from pleskdistup.common import action, dns, files, leapp_configs, log, motd, rpm, util


def _do_id_replacement(id: typing.Optional[str]) -> typing.Optional[str]:
    return leapp_configs.do_replacement(id, [
        lambda to_change: "alma9-" + to_change if not to_change.startswith("alma9-") else to_change,
    ])


def _do_name_replacement(name: typing.Optional[str]) -> typing.Optional[str]:
    return leapp_configs.do_replacement(name, [
        lambda to_change: "Alma " + to_change if not to_change.startswith("Alma ") else to_change,
        lambda to_change: to_change.replace("Enterprise Linux 8",  "Enterprise Linux 9"),
        lambda to_change: to_change.replace("EPEL-8", "EPEL-9"),
        lambda to_change: to_change.replace("$releasever", "9"),
    ])


def _fixup_old_php_urls(to_change: str) -> str:
    supported_old_versions = ["7.1", "7.2", "7.3"]
    for version in supported_old_versions:
        if "PHP_" + version in to_change:
            return to_change.replace("rpm-CentOS-8", "rpm-CentOS-9")
    return to_change


def _fix_rackspace_repository(to_change: str) -> str:
    if "mirror.rackspace.com" in to_change:
        return to_change.replace("rhel8-amd64", "rhel9-amd64")
    return to_change


def _fix_mariadb_repository(to_change: str) -> str:
    # Mariadb official repository doesn't support short url for centos 8 since 10.11
    # Since there are short URL for rhel8 short for all versions, we could use it instead
    if "yum.mariadb.org" in to_change:
        return to_change.replace("rhel8", "rhel9")
    return to_change


def _fix_rackspace_epel_repository(to_change: str) -> str:
    # The Rackspace EPEL repository for version 8 has a slightly different path, including 'Everything' in it
    # Additionally, some repositories use '7Server' instead of 7.
    # Therefore, we need to handle these cases specifically.
    if "iad.mirror.rackspace.com/epel/8/" in to_change:
        return to_change.replace("8", "9/Everything")
    if "iad.mirror.rackspace.com/epel/8Server" in to_change:
        return to_change.replace("8Server", "9/Everything")
    if "iad.mirror.rackspace.com/epel/8/Everything" in to_change:
        return to_change.replace("8/Everything", "9/Everything")
    return to_change


def _do_url_replacement(url: typing.Optional[str]) -> typing.Optional[str]:
    return leapp_configs.do_replacement(url, [
        _fixup_old_php_urls,
        _fix_rackspace_repository,
        _fix_mariadb_repository,
        _fix_rackspace_epel_repository,
        lambda to_change: to_change.replace("archives.fedoraproject.org/pub/archive/epel/8", "dl.fedoraproject.org/pub/epel/9/Everything"),
        lambda to_change: to_change.replace("rpm-RedHat-el8", "rpm-RedHat-el9"),
        lambda to_change: to_change.replace("rpm-CentOS-8", "rpm-RedHat-el9"),
        lambda to_change: to_change.replace("CloudLinux-8", "CloudLinux-9"),
        lambda to_change: to_change.replace("cloudlinux/8", "cloudlinux/9"),
        lambda to_change: to_change.replace("epel-8", "epel-9"),
        lambda to_change: to_change.replace("epel/8", "epel/9"),
        lambda to_change: to_change.replace("epel-debug-8", "epel-debug-9"),
        lambda to_change: to_change.replace("epel-source-8", "epel-source-9"),
        lambda to_change: to_change.replace("centos8", "centos9"),
        lambda to_change: to_change.replace("centos/8", "centos/9"),
        lambda to_change: to_change.replace("rhel/8", "rhel/9"),
        lambda to_change: to_change.replace("rhel8", "rhel9"),
        lambda to_change: to_change.replace("CentOS_8", "CentOS_9"),
        lambda to_change: to_change.replace("rhel-$releasever", "rhel-9"),
        lambda to_change: to_change.replace("$releasever", "9"),
        lambda to_change: to_change.replace("mirror.pp.plesk.tech/cloudlinux/8/os/", "mirror.pp.plesk.tech/cloudlinux/9/cloudlinux-x86_64-server-9/"),
        lambda to_change: to_change.replace("autoinstall.plesk.com/PMM_0.1.10", "autoinstall.plesk.com/PMM_0.1.11"),
        lambda to_change: to_change.replace("autoinstall.plesk.com/PMM0", "autoinstall.plesk.com/PMM_0.1.11"),
    ])


def _do_gpgkey_replacement(gpgkey: typing.Optional[str]) -> typing.Optional[str]:
    return leapp_configs.do_replacement(gpgkey, [
        lambda to_change: to_change.replace("EPEL-8", "EPEL-9"),
    ])


def _do_common_replacement(line: typing.Optional[str]) -> typing.Optional[str]:
    return leapp_configs.do_replacement(line, [
        lambda to_change: to_change.replace("EPEL-8", "EPEL-9"),
        # We can't check repository gpg because the key is not stored in the temporary file system
        # ToDo: Maybe we could find a way to put the key into the file system
        lambda to_change: to_change.replace("repo_gpgcheck = 1", "repo_gpgcheck = 0"),
    ])


def get_adapted_repository(
        repository: rpm.Repository,
        keep_id: bool = False
) -> rpm.Repository:
    id = _do_id_replacement(repository.id) if not keep_id else repository.id
    name = _do_name_replacement(repository.name)

    if id is None or name is None:
        raise ValueError(f"Repository {repository.id!r} with name {name!r} has no next id or next name")

    if repository.url is None and repository.metalink is None and repository.mirrorlist is None:
        raise ValueError(f"Repository {repository.id!r} has no next baseurl, metalink and mirrorlist")

    gpgkey_replacement = [_do_gpgkey_replacement(gpgkey) for gpgkey in repository.gpgkeys] if repository.gpgkeys else []

    return rpm.Repository(
        id,
        name=name,
        url=_do_url_replacement(repository.url) if repository.url else None,
        metalink=_do_url_replacement(repository.metalink) if repository.metalink else None,
        mirrorlist=_do_url_replacement(repository.mirrorlist) if repository.mirrorlist else None,
        enabled=repository.enabled,
        gpgcheck=repository.gpgcheck,
        gpgkeys=[gpgkey for gpgkey in gpgkey_replacement if gpgkey is not None] if gpgkey_replacement else None,
        additional=[sline for sline in (_do_common_replacement(line) for line in repository.additional) if sline is not None]
    )


class FixNamedConfig(action.ActiveAction):
    def __init__(self):
        self.name = "fix named configuration"
        self.named_conf = "/etc/named.conf"
        self.chrooted_configuration_path = "/var/named/chroot"

    def _is_required(self) -> bool:
        return os.path.exists(self.named_conf) and os.path.exists(os.path.join(self.chrooted_configuration_path, self.named_conf))

    def _handle_included_file(self, chrooted_file: str):
        target_file = chrooted_file.replace(self.chrooted_configuration_path, "")

        target_file_directory = os.path.dirname(target_file)
        if not os.path.exists(target_file_directory):
            os.makedirs(target_file_directory)

        if not os.path.exists(target_file):
            if os.path.exists(chrooted_file):
                os.symlink(chrooted_file, target_file)
            else:
                with open(target_file, "w") as _:
                    pass

        if os.path.getsize(target_file) == 0:
            with open(target_file, "w") as f:
                f.write("# centos2alma workaround commentary")

    def _prepare_action(self) -> action.ActionResult:
        for bind_configs in dns.get_all_includes_from_bind_config(self.named_conf, chroot_dir=self.chrooted_configuration_path):
            self._handle_included_file(bind_configs)

        return action.ActionResult()

    def _remove_included_files(self, chrooted_file: str):
        target_file = chrooted_file.replace(self.chrooted_configuration_path, "")
        if os.path.islink(target_file):
            os.unlink(target_file)

    def _post_action(self) -> action.ActionResult:
        for bind_configs in dns.get_all_includes_from_bind_config(self.named_conf, chroot_dir=self.chrooted_configuration_path):
            self._remove_included_files(bind_configs)

        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        for bind_configs in dns.get_all_includes_from_bind_config(self.named_conf, chroot_dir=self.chrooted_configuration_path):
            self._remove_included_files(bind_configs)

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
        if not os.path.exists(self.config_path):
            return action.ActionResult()

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
