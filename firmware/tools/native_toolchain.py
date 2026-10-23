Import("env")

import os
import shutil
import sys

MINGW_SPEC = "platformio/toolchain-gccmingw32@~1.50100.0"


def ensure_windows_gcc():
    if sys.platform != "win32":
        return
    env.Append(LINKFLAGS=["-static"])
    if shutil.which("gcc"):
        return
    from platformio.package.manager.tool import ToolPackageManager

    manager = ToolPackageManager()
    package = manager.get_package(MINGW_SPEC) or manager.install(MINGW_SPEC)
    env.PrependENVPath("PATH", os.path.join(package.path, "bin"))


ensure_windows_gcc()
