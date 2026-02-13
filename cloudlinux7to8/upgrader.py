# Copyright 2025. WebPros International GmbH. All rights reserved.

import argparse
import os
import typing

from pleskdistup import actions as common_actions
from pleskdistup.common import action, dist, feedback, files, version, util
from pleskdistup.phase import Phase
from pleskdistup.messages import REBOOT_WARN_MESSAGE
from pleskdistup.upgrader import DistUpgrader, DistUpgraderFactory, PathType

import cloudlinux7to8.config
from cloudlinux7to8 import actions as custom_actions


class CloudLinux7to8Upgrader(DistUpgrader):
    _distro_from = dist.CloudLinux("7")
    _distro_to = dist.CloudLinux("8")

    _pre_reboot_delay = 45

    def __init__(self):
        super().__init__()

        self.upgrade_postgres_allowed = False
        self.remove_unknown_perl_modules = False
        self.disable_spamassasin_plugins = False
        self.amavis_upgrade_allowed = False
        self.allow_raid_devices = False
        self.remove_leapp_logs = False
        self.allow_old_script_version = False

    def __repr__(self) -> str:
        attrs = ", ".join(f"{k}={getattr(self, k)!r}" for k in (
            "_distro_from", "_distro_to",
        ))
        return f"{self.__class__.__name__}({attrs})"

    def __str__(self) -> str:
        return f"{self.__class__.__name__}"

    @classmethod
    def supports(
        cls,
        from_system: typing.Optional[dist.Distro] = None,
        to_system: typing.Optional[dist.Distro] = None
    ) -> bool:
        return (
            (from_system is None or cls._distro_from == from_system)
            and (to_system is None or cls._distro_to == to_system)
        )

    @property
    def upgrader_name(self) -> str:
        return "Plesk::CloudLinux7to8Upgrader"

    @property
    def upgrader_version(self) -> str:
        if cloudlinux7to8.config.version:
            return cloudlinux7to8.config.version + "-" + cloudlinux7to8.config.revision[:8]
        return cloudlinux7to8.config.revision

    @property
    def issues_url(self) -> str:
        return "https://github.com/plesk/cloudlinux7to8/issues"

    def prepare_feedback(
        self,
        feed: feedback.Feedback,
    ) -> feedback.Feedback:

        feed.collect_actions += [
            feedback.collect_installed_packages_yum,
            feedback.collect_plesk_version,
            feedback.collect_kernel_modules,
        ]

        feed.attached_files += [
            "/etc/fstab",
            "/etc/grub2.cfg",
            "/etc/leapp/files/repomap.csv",
            "/etc/leapp/files/pes-events.json",
            "/etc/leapp/files/leapp_upgrade_repositories.repo",
            "/etc/named.conf",
            "/var/named/chroot/etc/named.conf",
            "/var/named/chroot/etc/named-user-options.conf",
            "/var/log/leapp/leapp-report.txt",
            "/var/log/leapp/leapp-preupgrade.log",
            "/var/log/leapp/leapp-upgrade.log",
        ]

        for grub_directory in ("/etc/grub.d", "/boot/grub", "/boot/grub2"):
            feed.attached_files += files.find_files_case_insensitive(grub_directory, ["*"])

        for repofile in files.find_files_case_insensitive("/etc/yum.repos.d", ["*.repo*"]):
            feed.attached_files.append(repofile)

        return feed

    def construct_actions(
        self,
        upgrader_bin_path: PathType,
        options: typing.Any,
        phase: Phase
    ) -> typing.Dict[str, typing.List[action.ActiveAction]]:
        new_os = str(self._distro_to)

        actions_map: typing.Dict[str, typing.List[action.ActiveAction]] = {
            "Status informing": [
                common_actions.HandleConversionStatus(options.status_flag_path, options.completion_flag_path),
                common_actions.AddFinishSshLoginMessage(new_os),  # Executed at the finish phase only
                common_actions.AddInProgressSshLoginMessage(new_os),
            ],
            "Leapp installation": [
                custom_actions.LeappInstallation(
                    custom_actions.LEAPP_CLOUDLINUX_RPM_URL,
                    [
                        "leapp-0.18.0-2.el7",
                        "python2-leapp-0.18.0-2.el7",
                        "leapp-data-cloudlinux-0.3-8.el7.20240821",
                        "leapp-deps-0.18.0-2.el7",
                        "leapp-upgrade-el7toel8-0.20.0-7.el7",
                        "leapp-upgrade-el7toel8-deps-0.20.0-7.el7",
                    ],
                    remove_logs_on_finish=self.remove_leapp_logs
                ),
            ],
            "Prepare finihsing systemd service": [
                common_actions.AddUpgradeSystemdService(
                    os.path.abspath(upgrader_bin_path),
                    options,
                ),
            ],
            "Prepare configurations": [
                common_actions.RevertChangesInGrub(),
                custom_actions.PrepareLeappConfigurationBackup(),
                custom_actions.RemoveOldMigratorThirdparty(),
                custom_actions.FetchKernelCareGPGKey(),
                custom_actions.FetchPleskGPGKey(),
                custom_actions.LeappReposConfiguration(),
                custom_actions.LeappChoicesConfiguration(),
                custom_actions.AdoptKolabRepositories(),
                custom_actions.AdoptAtomicRepositories(),
                custom_actions.PatchDnfpluginErrorOutput(),
                custom_actions.PatchLeappDebugNonAsciiPackager(),
                common_actions.UpdatePlesk(),
                custom_actions.PostgresReinstallModernPackage(),
                custom_actions.FixNamedConfig(),
                common_actions.DisablePleskSshBanner(),
                custom_actions.FixSyslogLogrotateConfig(options.state_dir),
                common_actions.SetMinDovecotDhParamSize(dhparam_size=2048),
                common_actions.RestoreDovecotConfiguration(options.state_dir),
                common_actions.RestoreRoundcubeConfiguration(options.state_dir),
                custom_actions.RecreateAwstatsConfigurationFiles(),
                common_actions.UninstallTuxcareEls(),
                common_actions.PreserveMariadbConfig(),
                common_actions.SubstituteSshPermitRootLoginConfigured(),
                custom_actions.UseSystemResolveForLeappContainer(),
            ],
            "Handle plesk related services": [
                common_actions.DisablePleskRelatedServicesDuringUpgrade(),
                common_actions.DisableServiceDuringUpgrade("mailman.service"),
                common_actions.HandlePleskFirewallService(),
            ],
            "Handle packages and services": [
                custom_actions.FixOsVendorPhpFpmConfiguration(),
                common_actions.RebundleRubyApplications(),
                custom_actions.ReinstallPhpmyadminPleskComponents(),
                custom_actions.ReinstallRoundcubePleskComponents(),
                custom_actions.ReinstallConflictPackages(options.state_dir),
                custom_actions.ReinstallMariadbConflictPackages(options.state_dir),
                custom_actions.ReinstallPerlCpanModules(options.state_dir),
                custom_actions.DisableSuspiciousKernelModules(),
                common_actions.HandleUpdatedSpamassassinConfig(),
                common_actions.DisableSelinuxDuringUpgrade(),
                custom_actions.RestoreMissingNginx(),
                common_actions.ReinstallAmavisAntivirus(),
                custom_actions.HandleInternetxRepository(),
                # We need to remove the python3-ethtool package because it causes issues on
                # CloudLinux 8 systems when multiple network interfaces are present.
                # This issue can block license activation, so we prefer to remove the package
                # to ensure the license remains valid after the conversion.
                common_actions.RemovePackagesOnFinish(
                    ["python3-ethtool"],
                    name="removing python3-ethtool package"
                ),
            ],
            "First plesk start": [
                common_actions.StartPleskBasicServices(),
            ],
            "Remove conflicting packages": [
                custom_actions.RemovingPleskConflictPackages(),
                custom_actions.RemovePleskOutdatedPackages(),
            ],
            "Update databases": [
                custom_actions.UpdateMariadbDatabase(),
                custom_actions.UpdateModernMariadb(),
                custom_actions.AddMysqlConnector(),
            ],
            "Repositories handling": [
                custom_actions.AdoptRepositories(),
                custom_actions.SwitchClnChannel(),
            ],
            "Do convert": [
                custom_actions.DisableBaseRepoUpdatesRepository(),
                custom_actions.RemovePleskBaseRepository(),
                custom_actions.DoCloudLinux7to8Convert(),
            ],
            "Resume": [
                common_actions.RestoreInProgressSshLoginMessage(new_os),
            ],
            "Pause before reboot": [
            ],
            "Reboot": [
                common_actions.Reboot(
                    prepare_next_phase=Phase.FINISH,
                    post_reboot=action.RebootType.AFTER_LAST_STAGE,
                    name="reboot and perform finishing actions",
                )
            ]
        }

        if not options.no_reboot:
            actions_map = util.merge_dicts_of_lists(actions_map, {
                "Pause before reboot": [
                    common_actions.PreRebootPause(
                        REBOOT_WARN_MESSAGE.format(delay=self._pre_reboot_delay, util_name="cloudlinux7to8"),
                        self._pre_reboot_delay
                    ),
                ]
            })

        if self.upgrade_postgres_allowed:
            actions_map = util.merge_dicts_of_lists(actions_map, {
                "Prepare configurations": [
                    custom_actions.PostgresDatabasesUpdate(),
                ]
            })

        return actions_map

    def get_check_actions(
        self,
        options: typing.Any,
        phase: Phase
    ) -> typing.List[action.CheckAction]:
        if phase is Phase.FINISH:
            return [custom_actions.AssertDistroIsCloudLinux8()]

        FIRST_SUPPORTED_BY_ALMA_8_PHP_VERSION = "5.6"
        CLOUDLINUX8_AMAVIS_REQUIRED_RAM = int(1.5 * 1024 * 1024 * 1024)
        checks = [
            common_actions.AssertPleskVersionIsAvailable(),
            common_actions.AssertPleskInstallerNotInProgress(),
            custom_actions.AssertAvailableSpaceForLocation("/var/lib", 5 * 1024 * 1024 * 1024),  # 5GB required minimum space to store packages
            custom_actions.AssertAvailableSpaceForLocation("/boot", 100 * 1024 * 1024),  # 100M required minimum space to store bootloader
            common_actions.AssertMinPhpVersionInstalled(FIRST_SUPPORTED_BY_ALMA_8_PHP_VERSION),
            common_actions.AssertMinPhpVersionUsedByWebsites(FIRST_SUPPORTED_BY_ALMA_8_PHP_VERSION),
            common_actions.AssertMinPhpVersionUsedByCron(FIRST_SUPPORTED_BY_ALMA_8_PHP_VERSION),
            common_actions.AssertOsVendorPhpUsedByWebsites(FIRST_SUPPORTED_BY_ALMA_8_PHP_VERSION),
            common_actions.AssertGrubInstalled(),
            custom_actions.AssertNoMoreThenOneKernelNamedNIC(),
            custom_actions.AssertRedHatKernelInstalled(),
            custom_actions.AssertLastInstalledKernelInUse(),
            custom_actions.AssertLocalRepositoryNotPresent(),
            custom_actions.AssertNoRepositoryDuplicates(),
            custom_actions.AssertMariadbRepoAvailable(),
            common_actions.AssertNotInContainer(),
            custom_actions.AssertPackagesUpToDate(),
            custom_actions.AssertNoOutdatedLetsEncryptExtRepository(),
            custom_actions.AssertPleskRepositoriesNotNoneLink(),
            custom_actions.AssertMinGovernorMariadbVersion(custom_actions.FIRST_SUPPORTED_GOVERNOR_MARIADB_VERSION),
            custom_actions.AssertGovernorMysqlNotInstalled(custom_actions.FIRST_SUPPORTED_GOVERNOR_MARIADB_VERSION),
            custom_actions.CheckSourcePointsToArchiveURL(),
            common_actions.AssertNoMoreThenOneKernelDevelInstalled(),
            common_actions.AssertEnoughRamForAmavis(CLOUDLINUX8_AMAVIS_REQUIRED_RAM, self.amavis_upgrade_allowed),
            common_actions.AssertSshPermitRootLoginConfigured(skip_known_substitudes=True),
            common_actions.AssertFstabOrderingIsFine(),
            common_actions.AssertFstabHasDirectRaidDevices(self.allow_raid_devices),
            common_actions.AssertFstabHasNoDuplicates(),
            common_actions.AssertPackageAvailable(
                "dnf",
                name="asserting dnf package available",
                recommendation="""The dnf package is required for Leapp to function properly.
\tHint: You can install it using the CentOS vault extras repository with the following base URL:
\t\t'baseurl=http://vault.centos.org/centos/$releasever/extras/$basearch/'"""
            ),
        ]

        if not self.upgrade_postgres_allowed:
            checks.append(custom_actions.AssertOutdatedPostgresNotInstalled())
        else:
            checks.append(custom_actions.AssertPostgresLocaleMatchesSystemOne())
        if not self.remove_unknown_perl_modules:
            checks.append(custom_actions.AssertThereIsNoUnknownPerlCpanModules())
        if not self.disable_spamassasin_plugins:
            checks.append(common_actions.AssertSpamassassinAdditionalPluginsDisabled())
        if not self.allow_old_script_version and cloudlinux7to8.config.version:
            checks.append(common_actions.AssertScriptVersionUpToDate("https://github.com/plesk/cloudlinux7to8", "cloudlinux7to8", version.DistupgradeToolVersion(cloudlinux7to8.config.version)))

        return checks

    def parse_args(self, args: typing.Sequence[str]) -> None:
        DESC_MESSAGE = f"""Use this upgrader to convert {self._distro_from} server with Plesk to {self._distro_to}.
The process consists of the following general stages:

-- Preparation (about 20 minutes) - The Leapp utility is installed and configured.
   The OS is prepared for the conversion. The Leapp utility is then called to
   create a temporary OS distribution.
-- Conversion (about 20 minutes) - The conversion takes place. During this stage,
   you cannot connect to the server via SSH.
-- Finalization (about 5 minutes) - The server is returned to normal operation.

To see the detailed plan, run the utility with the --show-plan option.

For assistance, submit an issue here {self.issues_url}
and attach the feedback archive generated with --prepare-feedback or at least
the log file.
"""
        parser = argparse.ArgumentParser(
            usage=argparse.SUPPRESS,
            description=DESC_MESSAGE,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            add_help=False,
        )
        parser.add_argument(
            "-h", "--help", action="help", default=argparse.SUPPRESS,
            help=argparse.SUPPRESS
        )
        parser.add_argument(
            "--upgrade-postgres", action="store_true", dest="upgrade_postgres_allowed", default=False,
            help="Upgrade all hosted PostgreSQL databases. To avoid data loss, create backups of all "
                 "hosted PostgreSQL databases before calling this option."
        )
        parser.add_argument(
            "--remove-unknown-perl-modules", action="store_true",
            dest="remove_unknown_perl_modules", default=False,
            help="Allow to remove unknown perl modules installed from CPAN. In this case all modules installed "
                 "by CPAN will be removed. Note that it could lead to some issues with perl scripts"
        )
        parser.add_argument(
            "--disable-spamassasin-plugins", action="store_true",
            dest="disable_spamassasin_plugins", default=False,
            help="Disable additional plugins in spamassasin configuration during the conversion."
        )
        parser.add_argument("--amavis-upgrade-allowed", action="store_true", dest="amavis_upgrade_allowed", default=False,
                            help="Allow to upgrade amavis antivirus even if there is not enough RAM available.")
        parser.add_argument("--allow-raid-devices", action="store_true", dest="allow_raid_devices", default=False,
                            help="Allow to have direct RAID devices in /etc/fstab. This could lead to unbootable system after the conversion so use the option on your own risk.")
        parser.add_argument("--remove-leapp-logs", action="store_true", dest="remove_leapp_logs", default=False,
                            help="Remove leapp logs after the conversion. By default, the logs are removed after the conversion.")
        parser.add_argument("--allow-old-script-version", action="store_true", dest="allow_old_script_version", default=False,
                            help="Allow to run the script with an old version. By default, the script checks for a new version on GitHub and does not allow to run with an old one.")
        options = parser.parse_args(args)

        self.upgrade_postgres_allowed = options.upgrade_postgres_allowed
        self.remove_unknown_perl_modules = options.remove_unknown_perl_modules
        self.disable_spamassasin_plugins = options.disable_spamassasin_plugins
        self.amavis_upgrade_allowed = options.amavis_upgrade_allowed
        self.allow_raid_devices = options.allow_raid_devices
        self.remove_leapp_logs = options.remove_leapp_logs
        self.allow_old_script_version = options.allow_old_script_version


class CloudLinux7to8Factory(DistUpgraderFactory):
    def __init__(self):
        super().__init__()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(upgrader_name={self.upgrader_name})"

    def __str__(self) -> str:
        return f"{self.__class__.__name__} (creates {self.upgrader_name})"

    def supports(
        self,
        from_system: typing.Optional[dist.Distro] = None,
        to_system: typing.Optional[dist.Distro] = None
    ) -> bool:
        return CloudLinux7to8Upgrader.supports(from_system, to_system)

    @property
    def upgrader_name(self) -> str:
        return "Plesk::CloudLinux7to8Upgrader"

    def create_upgrader(self, *args, **kwargs) -> DistUpgrader:
        return CloudLinux7to8Upgrader(*args, **kwargs)
