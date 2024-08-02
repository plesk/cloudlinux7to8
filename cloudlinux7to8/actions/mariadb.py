# Copyright 2024. WebPros International GmbH. All rights reserved.

import subprocess
import typing
import os

from pleskdistup.common import action, leapp_configs, files, log, mariadb, rpm, util


MARIADB_VERSION_ON_ALMA = mariadb.MariaDBVersion("10.3.39")
KNOWN_MARIADB_REPO_FILES = [
    "mariadb.repo",
    "mariadb10.repo",
    "cl-mysql.repo"
]
MARIADB_PACKAGES = [
    "MariaDB-client",
    "MariaDB-client-compat",
    "MariaDB-compat",
    "MariaDB-common",
    "MariaDB-server",
    "MariaDB-server-compat",
    "MariaDB-shared"
]


def _find_mariadb_repo_files() -> typing.List[str]:
    return files.find_files_case_insensitive("/etc/yum.repos.d", KNOWN_MARIADB_REPO_FILES)


def _is_governor_mariadb_installed() -> bool:
    if not mariadb.is_mariadb_installed() and not mariadb.is_mysql_installed():
        return False

    repofiles = _find_mariadb_repo_files()
    for repofile in repofiles:
        for repo in rpm.extract_repodata(repofile):
            _, _, repo_baseurl, _, _, _ = repo
            if repo_baseurl and "repo.cloudlinux.com" in repo_baseurl and ("cl-mariadb" in repo_baseurl or "cl-mysql" in repo_baseurl):
                return True

    return False


class AssertMariadbRepoAvailable(action.CheckAction):
    def __init__(self) -> None:
        self.name = "check mariadb repo available"
        self.description = """
The MariaDB repository with id '{}' from the file '{}' is not accessible.
\tThis issue may be caused by the deprecation of the currently installed MariaDB version or the disabling
\tof the MariaDB repository by the provider. To resolve this, update MariaDB to any version from the official
\trepository 'rpm.mariadb.org', or use the official archive repository for your current MariaDB version at 'archive.mariadb.org'.
"""

    def _do_check(self) -> bool:
        if not mariadb.is_mariadb_installed() or not mariadb.get_installed_mariadb_version() > MARIADB_VERSION_ON_ALMA:
            return True

        repofiles = _find_mariadb_repo_files()
        if len(repofiles) == 0:
            return True

        for repofile in repofiles:
            for repo in rpm.extract_repodata(repofile):
                repo_id, _, repo_baseurl, _, _, _ = repo
                if not repo_baseurl or ".mariadb.org" not in repo_baseurl:
                    continue

                # Since repository will be deprecated for any distro at once it looks fine to check only for 7 on x86_64
                repo_baseurl = repo_baseurl.replace("$releasever", "7").replace("$basearch", "x86_64")
                result = subprocess.run(["curl", "-s", "-o", "/dev/null", "-f", repo_baseurl])
                if result.returncode != 0:
                    self.description = self.description.format(repo_id, repofile)
                    return False

        return True


def _remove_mariadb_packages() -> None:
    rpm.remove_packages(rpm.filter_installed_packages(MARIADB_PACKAGES))


class UpdateModernMariadb(action.ActiveAction):
    def __init__(self) -> None:
        self.name = "update modern mariadb"

    def _is_required(self) -> bool:
        return mariadb.is_mariadb_installed() and mariadb.get_installed_mariadb_version() > MARIADB_VERSION_ON_ALMA and not _is_governor_mariadb_installed()

    def _prepare_action(self) -> action.ActionResult:
        repofiles = _find_mariadb_repo_files()
        if len(repofiles) == 0:
            raise Exception("Mariadb installed from unknown repository. Please check the '{}' file is present".format("/etc/yum.repos.d/mariadb.repo"))

        log.debug("Add MariaDB repository files '{}' mapping".format(repofiles[0]))
        leapp_configs.add_repositories_mapping(repofiles)

        log.debug("Set repository mapping in the leapp configuration file")
        leapp_configs.set_package_repository("mariadb", "alma-mariadb")
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        repofiles = _find_mariadb_repo_files()
        if len(repofiles) == 0:
            return action.ActionResult()

        for repofile in repofiles:
            leapp_configs.adopt_repositories(repofile)

        mariadb_repo_id, _1, _2, _3, _4, _5 = [repo for repo in rpm.extract_repodata(repofiles[0])][0]

        _remove_mariadb_packages()
        rpm.install_packages(["MariaDB-client", "MariaDB-server"], repository=mariadb_repo_id)
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 30

    def estimate_post_time(self) -> int:
        return 60


class UpdateMariadbDatabase(action.ActiveAction):
    def __init__(self) -> None:
        self.name = "updating mariadb databases"

    def _is_required(self) -> bool:
        return mariadb.is_mariadb_installed() and not mariadb.get_installed_mariadb_version() > MARIADB_VERSION_ON_ALMA and not _is_governor_mariadb_installed()

    def _prepare_action(self) -> action.ActionResult:
        _remove_mariadb_packages()
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        # Leapp does not remove non-standard MariaDB-client package. But since we have updated
        # mariadb to 10.3.35 old client is not relevant anymore. So we have to switch to new client.
        # On the other hand, we want to be sure AlmaLinux mariadb-server installed as well
        for repofile in _find_mariadb_repo_files():
            files.backup_file(repofile)
            os.unlink(repofile)

        _remove_mariadb_packages()
        rpm.install_packages(["mariadb", "mariadb-server"])

        # We should be sure mariadb is started, otherwise restore wouldn't work
        util.logged_check_call(["/usr/bin/systemctl", "start", "mariadb"])

        with open('/etc/psa/.psa.shadow', 'r') as shadowfile:
            shadowdata = shadowfile.readline().rstrip()
            util.logged_check_call(["/usr/bin/mysql_upgrade", "-uadmin", "-p" + shadowdata])
        # Also find a way to drop cookies, because it will ruin your day
        # We have to delete it once again, because leapp going to install it in scope of conversion process,
        # but without right configs
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()

    def estimate_post_time(self) -> int:
        return 2 * 60


FIRST_SUPPORTED_GOVERNOR_MARIADB_VERSION = mariadb.MariaDBVersion("10.2.44")


class AssertMinGovernorMariadbVersion(action.CheckAction):
    minimal_version: mariadb.MariaDBVersion

    def __init__(self, version: mariadb.MariaDBVersion) -> None:
        self.name = "check minimum guvernor mariadb version"
        self.minimal_version = version
        self.description = f"""
The installed version of MariaDB is incompatible with the conversion process. To proceed, update MariaDB using Governor to version {str(self.minimal_version)!r} or later.
"""

    def _do_check(self) -> bool:
        if not mariadb.is_mariadb_installed() or not _is_governor_mariadb_installed():
            return True

        return mariadb.get_installed_mariadb_version() >= self.minimal_version


class AssertGovernorMysqlNotInstalled(action.CheckAction):
    minimal_version: mariadb.MariaDBVersion

    def __init__(self, version: mariadb.MariaDBVersion) -> None:
        self.name = "check minimum governor mariadb version"
        self.minimal_version = version
        self.description = f"""
MySQL installed by Governor is not compatible with the conversion process. To continue, use Governor to update MariaDB to at least version {str(self.minimal_version)!r}.
"""

    def _do_check(self) -> bool:
        return not mariadb.is_mysql_installed() or not _is_governor_mariadb_installed()


class UpdateGuvernorMariadb(action.ActiveAction):
    def __init__(self) -> None:
        self.name = "update modern mariadb installed from governor"

    def _is_required(self) -> bool:
        if not mariadb.is_mariadb_installed() or not _is_governor_mariadb_installed():
            return False
        # Actually the version should be checked by the AssertMinGovernorMariadbVersion pre-checker
        # Therefore, if this execution occurs, we have likely forgotten to include the pre-checker in the process.
        if mariadb.get_installed_mariadb_version() < FIRST_SUPPORTED_GOVERNOR_MARIADB_VERSION:
            raise Exception(f"The installed version of MariaDB is not compatible with the conversion process. Please use Governor to update MariaDB to version {str(FIRST_SUPPORTED_GOVERNOR_MARIADB_VERSION)!r} or later.")

        return True

    def _prepare_action(self) -> action.ActionResult:
        repofiles = _find_mariadb_repo_files()
        if len(repofiles) == 0:
            raise Exception("Mariadb installed from unknown repository. Please check the '{}' file is present".format("/etc/yum.repos.d/mariadb.repo"))

        log.debug("Add MariaDB repository files '{}' mapping".format(repofiles[0]))
        leapp_configs.add_repositories_mapping(repofiles)

        # Unfortunately we can't rule source repositories for cl-MariaDB* packages at this point
        # because they based on dnf modules, which will not be available in scope of leapp script.
        # So we will have to reinstall packages after conversion process on CloudLinux 8 side.
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        repofiles = _find_mariadb_repo_files()
        if len(repofiles) == 0:
            return action.ActionResult()

        for repofile in repofiles:
            leapp_configs.adopt_repositories(repofile)

        mariadb_packages = rpm.get_installed_packages_list("cl-MariaDB*")
        mariadb_version = mariadb.get_installed_mariadb_version()
        mariadb_module = f"mariadb:cl-MariaDB{mariadb_version.major}{mariadb_version.minor}"
        log.debug(f"Going to reinstall following packages with enabled dnf module {mariadb_module!r}: {mariadb_packages}")

        rpm.remove_packages(rpm.filter_installed_packages(mariadb_packages))
        util.logged_check_call(["dnf", "module", "-y", "enable", mariadb_module])
        rpm.install_packages(mariadb_packages)

        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 30

    def estimate_post_time(self) -> int:
        return 60


class AddMysqlConnector(action.ActiveAction):
    def __init__(self) -> None:
        self.name = "install mysql connector"

    def _is_required(self) -> bool:
        return mariadb.is_mysql_installed()

    def _prepare_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        subprocess.check_call(["/usr/bin/dnf", "install", "-y", "mariadb-connector-c"])
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()
