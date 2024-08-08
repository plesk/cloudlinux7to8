# Copyright 2024. WebPros International GmbH. All rights reserved.
import os
import typing
import shutil

from pleskdistup.common import action, files, leapp_configs, log, motd, packages, rpm, systemd, util


class RemovingPleskConflictPackages(action.ActiveAction):
    conflict_pkgs: typing.List[str]

    def __init__(self) -> None:
        self.name = "remove plesk conflict packages"
        self.conflict_pkgs = [
            "openssl11-libs",
            "python36-PyYAML",
            "GeoIP",
            "psa-mod_proxy",
        ]

    def _prepare_action(self) -> action.ActionResult:
        packages.remove_packages(rpm.filter_installed_packages(self.conflict_pkgs))
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        packages.install_packages(self.conflict_pkgs)
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 2

    def estimate_revert_time(self) -> int:
        return 10


class ReinstallPleskComponents(action.ActiveAction):
    def __init__(self) -> None:
        self.name = "re-installing plesk components"

    def _prepare_action(self) -> action.ActionResult:
        components_pkgs = [
            "plesk-roundcube",
            "psa-phpmyadmin",
        ]

        packages.remove_packages(rpm.filter_installed_packages(components_pkgs))
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        # We should reinstall psa-phpmyadmin over plesk installer to make sure every trigger
        # will be called. It's because triggers that creates phpmyadmin configuration files
        # expect plesk on board. Hence when we install the package in scope of temporary OS
        # the file can't be created.
        packages.remove_packages(["psa-phpmyadmin"])
        util.logged_check_call(["/usr/sbin/plesk", "installer", "update"])

        util.logged_check_call(["/usr/sbin/plesk", "installer", "add", "--components", "roundcube"])
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        util.logged_check_call(["/usr/sbin/plesk", "installer", "update"])
        util.logged_check_call(["/usr/sbin/plesk", "installer", "add", "--components", "roundcube"])
        systemd.restart_services(["sw-cp-server"])
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 10

    def estimate_post_time(self) -> int:
        return 2 * 60

    def estimate_revert_time(self) -> int:
        return 6 * 60


class ReinstallConflictPackages(action.ActiveAction):
    removed_packages_file: str
    conflict_pkgs_map: typing.Dict[str, str]

    def __init__(self, temp_directory: str):
        self.name = "re-installing common conflict packages"
        self.removed_packages_file = temp_directory + "/cloudlinux7to8_removed_packages.txt"
        self.conflict_pkgs_map = {
            "galera": "galera",
            "python36-argcomplete": "python3-argcomplete",
            "python36-cffi": "python3-cffi",
            "python36-chardet": "python3-chardet",
            "python36-colorama": "python3-colorama",
            "python36-cryptography": "python3-cryptography",
            "python36-pycurl": "python3-pycurl",
            "python36-dateutil": "python3-dateutil",
            "python36-dbus": "python3-dbus",
            "python36-decorator": "python3-decorator",
            "python36-gobject-base": "python3-gobject-base",
            "python36-idna": "python3-idna",
            "python36-jinja2": "python3-jinja2",
            "python36-jsonschema": "python3-jsonschema",
            "python36-jwt": "python3-jwt",
            "python36-lxml": "python3-lxml",
            "python36-markupsafe": "python3-markupsafe",
            "python36-pyOpenSSL": "python3-pyOpenSSL",
            "python36-ply": "python3-ply",
            "python36-prettytable": "python3-prettytable",
            "python36-pycparser": "python3-pycparser",
            "python36-pyparsing": "python3-pyparsing",
            "python36-pyserial": "python3-pyserial",
            "python36-pytz": "python3-pytz",
            "python36-requests": "python3-requests",
            "python36-six": "python3-six",
            "python36-urllib3": "python3-urllib3",
            "libpcap": "libpcap",
            "libwebp7": "libwebp",
            "libzip5": "libzip",
            "libytnef": "ytnef",
        }

    def _is_required(self) -> bool:
        return len(rpm.filter_installed_packages(list(self.conflict_pkgs_map.keys()))) > 0

    def _prepare_action(self) -> action.ActionResult:
        packages_to_remove = rpm.filter_installed_packages(list(self.conflict_pkgs_map.keys()))

        rpm.remove_packages(packages_to_remove)

        with open(self.removed_packages_file, "a") as f:
            f.write("\n".join(packages_to_remove) + "\n")

        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        if not os.path.exists(self.removed_packages_file):
            log.warn("File with removed packages list does not exist. While the action itself was not skipped. Skip reinstalling packages.")
            return action.ActionResult()

        with open(self.removed_packages_file, "r") as f:
            packages_to_install = [self.conflict_pkgs_map[pkg] for pkg in set(f.read().splitlines())]
            rpm.install_packages(packages_to_install)

        os.unlink(self.removed_packages_file)
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        if not os.path.exists(self.removed_packages_file):
            log.warn("File with removed packages list does not exist. While the action itself was not skipped. Skip reinstalling packages.")
            return action.ActionResult()

        with open(self.removed_packages_file, "r") as f:
            packages_to_install = list(set(f.read().splitlines()))
            rpm.install_packages(packages_to_install)

        os.unlink(self.removed_packages_file)
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 10

    @property
    def _removed_packages_num(self) -> int:
        if os.path.exists(self.removed_packages_file):
            with open(self.removed_packages_file, "r") as f:
                return len(f.read().splitlines())
        return 0

    def estimate_post_time(self) -> int:
        return 60 + 10 * self._removed_packages_num

    def estimate_revert_time(self) -> int:
        return 60 + 10 * self._removed_packages_num


CHANGED_REPOS_MSG_FMT = """During the conversion, some of customized .repo files were updated. You can find the old
files with the .rpmsave extension. Below is a list of the changed files:
\t{changed_files}
"""


class AdoptRepositories(action.ActiveAction):
    def __init__(self) -> None:
        self.name = "adopting repositories"

    def _prepare_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _use_rpmnew_repositories(self) -> None:
        # The problem is about changed repofiles, that leapp is trying to install from packages.
        # For example, when epel.repo file was changed, dnf will save the new one as epel.repo.rpmnew.
        # I beleive there could be other files with the same problem, so let's iterate every .rpmnew file in /etc/yum.repos.d
        fixed_list = []
        for file in files.find_files_case_insensitive("/etc/yum.repos.d", ["*.rpmnew"]):
            original_file = file[:-len(".rpmnew")]
            if os.path.exists(original_file):
                shutil.move(original_file, original_file + ".rpmsave")
                fixed_list.append(original_file)

            shutil.move(file, original_file)

        if len(fixed_list) > 0:
            motd.add_finish_ssh_login_message(CHANGED_REPOS_MSG_FMT.format(changed_files="\n\t".join(fixed_list)))

    def _adopt_plesk_repositories(self) -> None:
        for file in files.find_files_case_insensitive("/etc/yum.repos.d", ["plesk*.repo"]):
            rpm.remove_repositories(file, [
                lambda id, _1, _2, _3, _4: id in ["PLESK_17_PHP52", "PLESK_17_PHP53",
                                                  "PLESK_17_PHP54", "PLESK_17_PHP55",
                                                  "PLESK_17_PHP56", "PLESK_17_PHP70"],
            ])
            leapp_configs.adopt_repositories(file)

    def _post_action(self) -> action.ActionResult:
        self._use_rpmnew_repositories()
        self._adopt_plesk_repositories()
        util.logged_check_call(["/usr/bin/dnf", "-y", "update"])
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()

    def estimate_post_time(self) -> int:
        return 2 * 60


class RemovePleskBaseRepository(action.ActiveAction):
    # In some cases we have plesk specific base repository, which will not be
    # fixed by the leapp converter. So we have to remove it manually.
    base_repo_path: str = "/etc/yum.repos.d/base.repo"

    def __init__(self) -> None:
        self.name = "removing base repository"

    def _is_required(self) -> bool:
        return os.path.exists(self.base_repo_path)

    def _prepare_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _is_plesk_base(self, repo_file: str) -> bool:
        for id, _2, baseurl, _3, _4, _5 in rpm.extract_repodata(repo_file):
            if baseurl and "psabr.aws.plesk.tech/share/mirror/cloudlinux/7" in baseurl:
                log.info(f"Plesk base repo found in {repo_file!r} by repository {id!r}")
                return True
        return False

    def _post_action(self) -> action.ActionResult:
        if os.path.exists(self.base_repo_path):
            if self._is_plesk_base(self.base_repo_path):
                files.backup_file(self.base_repo_path)
                os.unlink(self.base_repo_path)
                return action.ActionResult()

        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()


class AssertPleskRepositoriesNotNoneLink(action.CheckAction):
    def __init__(self):
        self.name = "checking if plesk repositories does not have a 'none' link"
        self.description = """There are plesk repositories with link set to 'none'. To proceed with the conversion, remove following repositories:
\t- {}
"""

    def _do_check(self) -> bool:
        none_link_repos = []
        for file in files.find_files_case_insensitive("/etc/yum.repos.d", ["plesk*.repo"]):
            for id, _2, url, metalink, mirrorlist, _5 in rpm.extract_repodata(file):
                if rpm.repository_has_none_link(id, None, url, metalink, mirrorlist):
                    none_link_repos.append(f"'{id}' from repofile '{file}'")

        if len(none_link_repos) == 0:
            return True

        self.description = self.description.format("\n\t- ".join(none_link_repos))
        return False


class AssertIPRepositoryNotPresent(action.CheckAction):
    def __init__(self):
        self.name = "verify the presence of a repository sourced from an IP address"
        self.description = """There is an RPM repository from a source host with an IP address.
\tWe cannot confirm if this repository's packages conflict with AlmaLinux's official repositories.
\tTo proceed with the conversion, please remove the repositories listed in the following .repo files:
\t- {}
"""

    def _is_repo_source_ip_address(self, repo_file) -> bool:
        for _1, _2, url, metalink, mirrorlist, _5 in rpm.extract_repodata(repo_file):
            if rpm.repository_source_is_ip(url, metalink, mirrorlist):
                return True
        return False

    def _do_check(self) -> bool:
        ip_source_repositories_files = [file for file in files.find_files_case_insensitive("/etc/yum.repos.d", ["*.repo"])
                                        if self._is_repo_source_ip_address(file)]

        if len(ip_source_repositories_files) == 0:
            return True

        self.description = self.description.format("\n\t- ".join(ip_source_repositories_files))
        return False



class RemoveOldMigratorThirdparty(action.ActiveAction):
    def __init__(self) -> None:
        self.name = "removing old migrator thirdparty packages"

    def _find_migrator_repo_files(self) -> typing.List[str]:
        return files.find_files_case_insensitive("/etc/yum.repos.d", ["plesk*migrator*.repo"])

    def _is_required(self) -> bool:
        for file in self._find_migrator_repo_files():
            for _1, _2, url, _3, _4, _5 in rpm.extract_repodata(file):
                if url and "PMM_0.1.10/thirdparty-rpm" in url:
                    return True

        return False

    def _prepare_action(self) -> action.ActionResult:
        for file in self._find_migrator_repo_files():
            files.backup_file(file)

            rpm.remove_repositories(file, [
                lambda _1, _2, baseurl, _3, _4: (baseurl is not None and "PMM_0.1.10/thirdparty-rpm" in baseurl),
            ])
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        for file in self._find_migrator_repo_files():
            files.remove_backup(file)
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        for file in self._find_migrator_repo_files():
            files.restore_file_from_backup(file)
        return action.ActionResult()


class RestoreMissingNginx(action.ActiveAction):
    def __init__(self) -> None:
        self.name = "restore nginx if it was removed during the conversion"

    def _is_required(self) -> bool:
        # nginx related to plesk could be removed by user. So we need to make sure
        # it is installed before we start the conversion
        return packages.is_package_installed("sw-nginx")

    def _prepare_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        if not packages.is_package_installed("sw-nginx"):
            util.logged_check_call(["/usr/sbin/plesk", "installer", "add", "--components", "nginx"])
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()

    def estimate_post_time(self) -> int:
        return 3 * 60


class AssertNoOutdatedLetsEncryptExtRepository(action.CheckAction):
    OUTDATED_LETSENCRYPT_REPO_PATHS = ["/etc/yum.repos.d/plesk-letsencrypt.repo", "/etc/yum.repos.d/plesk-ext-letsencrypt.repo"]

    def __init__(self) -> None:
        self.name = "checking if outdated repository for letsencrypt extension is used"
        self.description = """There is outdated repository for letsencrypt extension used.
\tTo resolve the problem perform following actions:
\t1. make sure the letsencrypt extension is up to date from Plesk web interface
\t2. rpm -qe plesk-letsencrypt-pre plesk-py27-pip plesk-py27-setuptools plesk-py27-virtualenv plesk-wheel-cffi plesk-wheel-cryptography plesk-wheel-psutil
\t3. rm {repo_paths}
"""

    def _do_check(self) -> bool:
        for path in self.OUTDATED_LETSENCRYPT_REPO_PATHS:
            if os.path.exists(path):
                self.description = self.description.format(repo_paths=path)
                return False
        return True


class AdoptAtomicRepositories(action.ActiveAction):
    atomic_repository_path: str = "/etc/yum.repos.d/tortix-common.repo"

    def __init__(self) -> None:
        self.name = "adopting atomic repositories"

    def _is_required(self) -> bool:
        return os.path.exists(self.atomic_repository_path)

    def _prepare_action(self) -> action.ActionResult:
        leapp_configs.add_repositories_mapping([self.atomic_repository_path])
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        # We don't need to adopt repositories here because repositories uses $releasever-$basearch
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()
