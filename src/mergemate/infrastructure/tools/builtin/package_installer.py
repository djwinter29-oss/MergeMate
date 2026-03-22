"""Built-in package installer tool with explicit config gating."""

from __future__ import annotations

import subprocess


class PackageInstallerTool:
    name = "package_installer"

    def __init__(
        self,
        *,
        allow_package_install: bool,
        allowed_packages: list[str],
        pip_executable: str,
    ) -> None:
        self._allow_package_install = allow_package_install
        self._allowed_packages = set(allowed_packages)
        self._pip_executable = pip_executable

    def invoke(self, payload: dict[str, str]) -> dict[str, str]:
        package_name = payload.get("package_name", "").strip()
        if not self._allow_package_install:
            return {"status": "blocked", "detail": "Package installation is disabled by configuration."}
        if not package_name:
            return {"status": "error", "detail": "package_name is required."}
        if self._allowed_packages and package_name not in self._allowed_packages:
            return {
                "status": "blocked",
                "detail": f"Package {package_name} is not in the allowed_packages list.",
            }

        command = [self._pip_executable, "-m", "pip", "install", package_name]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            return {
                "status": "error",
                "detail": completed.stderr.strip() or completed.stdout.strip() or "pip install failed",
            }

        return {
            "status": "installed",
            "detail": completed.stdout.strip() or f"Installed {package_name}",
        }