from types import SimpleNamespace

from wraplab import runtime_identity


def test_windows_identity_needs_no_wmi_shell_or_hardware_probe(monkeypatch):
    def forbidden():
        raise AssertionError("Windows report identity must not call platform's WMI/shell fallback")

    monkeypatch.setattr(runtime_identity, "sys", SimpleNamespace(
        platform="win32",
        getwindowsversion=lambda: SimpleNamespace(major=10, minor=0, build=26100),
    ))
    monkeypatch.setattr(runtime_identity, "platform", SimpleNamespace(
        system=forbidden, platform=forbidden, machine=forbidden,
    ))
    monkeypatch.setattr(runtime_identity, "sysconfig", SimpleNamespace(get_platform=lambda: "win-amd64"))
    assert runtime_identity.platform_name() == "Windows"
    assert runtime_identity.os_version() == "Windows-10.0.26100"
    assert runtime_identity.architecture() == "amd64"
