import subprocess

from mergemate.infrastructure.tools.builtin.package_installer import PackageInstallerTool


def test_package_installer_respects_configuration_gates() -> None:
    tool = PackageInstallerTool(allow_package_install=False, allowed_packages=[], pip_executable="python3", timeout_seconds=30)

    assert tool.invoke({"package_name": "requests"})["status"] == "blocked"

    allowed_tool = PackageInstallerTool(allow_package_install=True, allowed_packages=["requests"], pip_executable="python3", timeout_seconds=30)
    assert allowed_tool.invoke({"package_name": ""})["status"] == "error"
    assert allowed_tool.invoke({"package_name": "flask"})["status"] == "blocked"


def test_package_installer_reports_subprocess_result(monkeypatch) -> None:
    calls = []

    def fake_run(command, capture_output, text, check, timeout):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="installed", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    tool = PackageInstallerTool(allow_package_install=True, allowed_packages=[], pip_executable="python3", timeout_seconds=30)

    result = tool.invoke({"package_name": "requests"})

    assert result == {"status": "installed", "detail": "installed"}
    assert calls == [["python3", "-m", "pip", "install", "requests"]]


def test_package_installer_surfaces_subprocess_error(monkeypatch) -> None:
    def fake_run(command, capture_output, text, check, timeout):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="failed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    tool = PackageInstallerTool(allow_package_install=True, allowed_packages=[], pip_executable="python3", timeout_seconds=30)

    result = tool.invoke({"package_name": "requests"})

    assert result == {"status": "error", "detail": "failed"}


def test_package_installer_surfaces_missing_executable(monkeypatch) -> None:
    def fake_run(command, capture_output, text, check, timeout):
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(subprocess, "run", fake_run)
    tool = PackageInstallerTool(allow_package_install=True, allowed_packages=[], pip_executable="python3", timeout_seconds=30)

    result = tool.invoke({"package_name": "requests"})

    assert result == {"status": "error", "detail": "Executable python3 was not found."}


def test_package_installer_surfaces_timeout(monkeypatch) -> None:
    def fake_run(command, capture_output, text, check, timeout):
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)
    tool = PackageInstallerTool(allow_package_install=True, allowed_packages=[], pip_executable="python3", timeout_seconds=18)

    result = tool.invoke({"package_name": "requests"})

    assert result == {"status": "error", "detail": "pip install timed out after 18s."}