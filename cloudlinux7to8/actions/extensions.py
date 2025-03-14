# Copyright 2025. WebPros International GmbH. All rights reserved.

import os
import typing
import urllib.request

from pleskdistup.common import action, util, leapp_configs, log, plesk, rpm, files


class FixupImunify(action.ActiveAction):
    def __init__(self):
        self.name = "fixing up imunify360"

    def _find_imunify_repo_files(self) -> typing.List[str]:
        return files.find_files_case_insensitive("/etc/yum.repos.d", ["imunify*.repo"])

    def _is_required(self) -> bool:
        return len(self._find_imunify_repo_files()) > 0

    def _prepare_action(self) -> action.ActionResult:
        repofiles = self._find_imunify_repo_files()

        leapp_configs.add_repositories_mapping(repofiles)

        # For some reason leapp replaces the libssh2 package on installation. It's fine in most cases,
        # but imunify packages require libssh2. So we should use PRESENT action to keep it.
        leapp_configs.set_package_action("libssh2", leapp_configs.LeappActionType.PRESENT)
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()


class AdoptKolabRepositories(action.ActiveAction):
    def __init__(self):
        self.name = "adopting kolab repositories"

    def _find_kolab_repo_files(self) -> typing.List[str]:
        return files.find_files_case_insensitive("/etc/yum.repos.d", ["kolab*.repo"])

    def _is_required(self) -> bool:
        return len(self._find_kolab_repo_files()) > 0

    def _prepare_action(self) -> action.ActionResult:
        repofiles = self._find_kolab_repo_files()

        leapp_configs.add_repositories_mapping(
            repofiles,
            ignore=[
                "kolab-16-source",
                "kolab-16-testing-source",
                "kolab-16-testing-candidate-source",
            ]
        )
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        for file in self._find_kolab_repo_files():
            leapp_configs.adopt_repositories(file)

        util.logged_check_call(["/usr/bin/dnf", "-y", "update"])
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 30

    def estimate_post_time(self) -> int:
        return 2 * 60


class FetchKernelCareGPGKey(action.ActiveAction):
    """This action fetches the KernelCare GPG key from the configured repository for leapp.
    Usually leapp brings all required GPG keys with it inside specific configuration directory.
    But KernelCare is not supported by AlmaLinux, so we need to fetch the GPG key manually to make
    sure leapp will be able to proceed with the conversion when packages from KernelCare repository installed.
    """

    kernelcare_repofile: str = "/etc/yum.repos.d/kernelcare.repo"
    leapp_gpg_keys_store: str = "/etc/leapp/files/vendors.d/rpm-gpg"

    def __init__(self):
        self.name = "fetching KernelCare GPG key"
        self.kernelcare_gpg_keys_urls = self._get_kernelcare_gpg_keys_urls()

    def _is_kernelcare_extension_installed(self) -> bool:
        return "kernelcare-plesk" in dict(plesk.list_installed_extensions())

    def _is_kernelcare_gpg_key_missing(self) -> bool:
        return any(
            not os.path.exists(self._get_kernelcare_gpg_target_path(key_url))
            for key_url in self.kernelcare_gpg_keys_urls
        )

    def _is_required(self) -> bool:
        return self._is_kernelcare_extension_installed() and self._is_kernelcare_gpg_key_missing()

    def _get_kernelcare_gpg_keys_urls(self) -> typing.List[str]:
        if not os.path.exists(self.kernelcare_repofile):
            return []

        result = []
        for repo_id, _, _, _, _, additional in rpm.extract_repodata(self.kernelcare_repofile):
            if repo_id != "kernelcare":
                continue

            for line in additional:
                if line.startswith("gpgkey="):
                    result.append(line[len("gpgkey="):].rstrip())

        return result

    def _get_kernelcare_gpg_target_path(self, key_url: str) -> str:
        return f"{self.leapp_gpg_keys_store}/{key_url.split('/')[-1]}"

    def _prepare_action(self) -> action.ActionResult:
        for key_url in self.kernelcare_gpg_keys_urls:
            gpg_key_target_path = self._get_kernelcare_gpg_target_path(key_url)
            log.debug(f"Going to save KernelCare GPG key from {key_url!r} to {gpg_key_target_path!r}")
            if os.path.exists(gpg_key_target_path):
                continue

            try:
                with urllib.request.urlopen(key_url) as response:
                    with open(gpg_key_target_path, 'wb') as out_file:
                        out_file.write(response.read())
            except Exception as e:
                raise RuntimeError(
                    f"Unable to fetch KernelCare GPG key from '{key_url}': {e}. "
                    f"To continue with the conversion, please manually install the key into "
                    f"'{self.leapp_gpg_keys_store}' or remove the KernelCare extension."
                ) from e

        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        # Since it's part of leapp configuration, it is fine to keep the key in the store.
        return action.ActionResult()
