# Copyright 2025. WebPros International GmbH. All rights reserved.

import collections
import os
import shutil
import subprocess
import typing

from pleskdistup.common import action, dist, files, log, version


class AssertDistroIsCloudLinux8(action.CheckAction):
    def __init__(self) -> None:
        self.name = "checking if distro is CloudLinux 8"
        self.description = "You are running a distribution other than CloudLinux 8. The finalization stage can only be started on CloudLinux 8."

    def _do_check(self) -> bool:
        return dist.get_distro() == dist.CloudLinux("8")


class AssertNoMoreThenOneKernelNamedNIC(action.CheckAction):
    def __init__(self) -> None:
        self.name = "checking if there is more than one NIC interface using ketnel-name"
        self.description = """The system has one or more network interface cards (NICs) using kernel-names (ethX).
\tLeapp cannot guarantee the interface names' stability during the conversion.
\tGive those NICs persistent names (enpXsY) to proceed with the conversion.
\tInterfaces: {}
"""

    def _do_check(self) -> bool:
        # We can't use this method to get interfaces names, so just skip the check
        if not os.path.exists("/sys/class/net"):
            return True

        interfaces = os.listdir('/sys/class/net')
        suspicious_interfaces = [interface for interface in interfaces if interface.startswith("eth") and interface[3:].isdigit()]
        if len(suspicious_interfaces) > 1:
            self.description = self.description.format(", ".join(suspicious_interfaces))
            return False

        return True


# ToDo. Implement for deb-based and move to common part. Might be useful for distupgrade/other converters
class AssertLastInstalledKernelInUse(action.CheckAction):
    def __init__(self) -> None:
        self.name = "checking if the last installed kernel is in use"
        self.description = """The last installed kernel is not in use.
\tThe kernel version in use is '{}'. The last installed kernel version is '{}'.
\tReboot the system to use the last installed kernel.
"""

    def _get_kernel_version_in_use(self) -> version.KernelVersion:
        curr_kernel = subprocess.check_output(["/usr/bin/uname", "-r"], universal_newlines=True).strip()
        log.debug("Current kernel version is '{}'".format(curr_kernel))
        return version.KernelVersion(curr_kernel)

    def _get_last_installed_kernel_version(self) -> version.KernelVersion:
        versions = subprocess.check_output(
            [
                "/usr/bin/rpm", "-q", "-a", "kernel", "kernel-plus", "kernel-rt-core"
            ], universal_newlines=True
        ).splitlines()

        log.debug("Installed kernel versions: {}".format(', '.join(versions)))
        return max([version.KernelVersion(ver) for ver in versions])

    def _do_check(self) -> bool:
        last_installed_kernel_version = self._get_last_installed_kernel_version()
        used_kernel_version = self._get_kernel_version_in_use()

        if used_kernel_version != last_installed_kernel_version:
            self.description = self.description.format(str(used_kernel_version), str(last_installed_kernel_version))
            return False

        return True


class AssertRedHatKernelInstalled(action.CheckAction):
    def __init__(self) -> None:
        self.name = "checking if the Red Hat kernel is installed"
        self.description = """No Red Hat signed kernel is installed.
\tTo proceed with the conversion, install a kernel by running:
\t- 'yum install kernel kernel-tools kernel-tools-libs'
\tAfter installing the kernel fix the grub configuration by calling:
\t- `grub2-set-default 'CentOS Linux (newly_installed_kernel_version) 7 (Core)'`
\t- `grub2-mkconfig -o /boot/grub2/grub.cfg`
\t- `reboot`
"""

    def _do_check(self) -> bool:
        redhat_kernel_packages = subprocess.check_output(
            [
                "/usr/bin/rpm", "-q", "-a", "kernel", "kernel-rt"
            ], universal_newlines=True
        ).splitlines()
        return len(redhat_kernel_packages) > 0


def _find_repo_files() -> typing.List[str]:
    return files.find_files_case_insensitive("/etc/yum.repos.d", "*.repo")


class AssertLocalRepositoryNotPresent(action.CheckAction):
    def __init__(self):
        self.name = "checking if the local repository is present"
        self.description = """There are rpm repositories with local storage present. Leapp is not support such kind of repositories.
\tPlease remove the local repositories to proceed the conversion. Files where locally stored repositories are defined:
\t- {}
"""

    def _is_repo_with_local_storage(self, repo_file) -> bool:
        with open(repo_file) as f:
            repository_content = f.read()
            return ("baseurl=file:" in repository_content or "baseurl = file:" in repository_content or
                    "metalink=file:" in repository_content or "metalink = file:" in repository_content or
                    "mirrorlist=file:" in repository_content or "mirrorlist = file:" in repository_content)

    def _do_check(self) -> bool:
        # CentOS-Media.repo is a special file which is created by default on CentOS 7. It contains a local repository
        # but leapp allows it anyway. So we could skip it.
        local_repositories_files = [
            file for file in _find_repo_files()
            if os.path.basename(file) != "CentOS-Media.repo" and self._is_repo_with_local_storage(file)
        ]

        if len(local_repositories_files) == 0:
            return True

        self.description = self.description.format("\n\t- ".join(local_repositories_files))
        return False


class AssertNoRepositoryDuplicates(action.CheckAction):
    def __init__(self) -> None:
        self.name = "checking if there are duplicate repositories"
        self.description = """There are duplicate repositories present:
\t- {}

\tPlease remove duplicates to proceed the conversion.
"""

    def _do_check(self) -> bool:
        repositories = []
        repofiles = _find_repo_files()
        for repofile in repofiles:
            with open(repofile, "r") as f:
                for line in f.readlines():
                    line = line.strip()
                    if line.startswith("[") and line.endswith("]"):
                        repositories.append(line)

        duplicates = [repository for repository, count in collections.Counter(repositories).items() if count > 1]
        if len(duplicates) == 0:
            return True

        self.description = self.description.format("\n\t- ".join(duplicates))
        return False


class AssertPackagesUpToDate(action.CheckAction):
    def __init__(self):
        self.name = "checking if all packages are up to date"
        self.description = "There are packages which are not up to date. Call `yum update -y && reboot` to update the packages.\n"

    def _do_check(self) -> bool:
        subprocess.check_call(["/usr/bin/yum", "clean", "all"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        checker = subprocess.run(["/usr/bin/yum", "check-update"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return checker.returncode == 0


class AssertAvailableSpace(action.CheckAction):
    def __init__(self) -> None:
        self.name = "checking available space"
        self.required_space = 5 * 1024 * 1024 * 1024  # 5GB
        self.description = """There is insufficient disk space available. Leapp requires a minimum of {} of free space
\ton the disk where the '/var/lib' directory is located. Available space: {}.
\tFree up enough disk space and try again.
"""

    def _get_human_readable_size(self, size) -> str:
        original = size
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{original} B"

    def _do_check(self) -> bool:
        # Leapp stores rhel 8 filesystem in /var/lib/leapp
        # That's why it takes so much disk space
        available_space = shutil.disk_usage("/var/lib")[2]
        if available_space >= self.required_space:
            return True

        self.description = self.description.format(self._get_human_readable_size(self.required_space), self._get_human_readable_size(available_space))
        return False
