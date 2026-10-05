"""Basic report identity without Windows WMI, shell commands or hardware enumeration."""

import platform
import sys
import sysconfig


def platform_name():
    return "Windows" if sys.platform == "win32" else platform.system()


def os_version():
    if sys.platform == "win32":
        v = sys.getwindowsversion()
        return f"Windows-{v.major}.{v.minor}.{v.build}"
    return platform.platform()


def architecture():
    if sys.platform == "win32":
        return sysconfig.get_platform().removeprefix("win-")
    return platform.machine()
