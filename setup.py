"""
Wheel and source-wrapper packaging configuration for orekit-nrlmsis21.

All static project metadata (name, version, dependencies, license files, ...) is declared in
pyproject.toml. This file configures ``package_data`` and wheel tags for two supported modes:

1. Source-Wrapper Distribution Mode (``OREKIT_NRLMSIS21_WRAPPER_ONLY=1``):
   Designed for public distribution where users obtain NRLMSIS 2.1 independently from NRL and
   compile it locally. Excludes:
   - ``external/NRLMSIS2.1/*.F90`` (upstream NRL Fortran 2003 sources)
   - ``external/NRLMSIS2.1/msis21.parm`` (upstream NRL parameter table)
   - ``python/orekit_nrlmsis21/lib/*.dll`` and ``lib/*.so*`` (compiled NRLMSIS 2.1 native binaries)
   - ``python/orekit_nrlmsis21/lib/*.parm`` (duplicate bundled ``msis21.parm`` parameter table)
   Includes only the Python wrapper modules, the Java Orekit adapter JAR (``lib/*.jar``), and
   required license/attribution notices. Produces a platform-independent ``py3-none-any`` wheel.

2. Local Development / Precompiled Binary Mode (default, ``OREKIT_NRLMSIS21_WRAPPER_ONLY=0``):
   Preserves current development and test workflows by bundling the platform-specific JNI binary
   (``.dll`` on Windows, ``.so*`` on Linux), ``lib/*.jar``, and ``lib/*.parm``, tagged as
   ``py3-none-<platform>``.
"""
import os
import pathlib
import shutil
import sys

from setuptools import setup

try:  # setuptools >= 70.1
    from setuptools.command.bdist_wheel import bdist_wheel as _bdist_wheel
except ImportError:  # pragma: no cover - older setuptools
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel


WRAPPER_ONLY = os.environ.get("OREKIT_NRLMSIS21_WRAPPER_ONLY", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)

if WRAPPER_ONLY and os.path.exists("build/wrapper_only"):
    shutil.rmtree("build/wrapper_only")

BUILD_OPTIONS = {"build": {"build_base": "build/wrapper_only"}} if WRAPPER_ONLY else {}

# Stage CMakeLists.txt + native bridge sources into _native_src/ during wheel builds
# so `orekit-nrlmsis21-setup` works from a pip-installed wheel without cloning the repo.
_REPO_ROOT = pathlib.Path(__file__).resolve().parent
_NATIVE_SRC_STAGE = _REPO_ROOT / "python" / "orekit_nrlmsis21" / "_native_src"
if WRAPPER_ONLY and (_REPO_ROOT / "CMakeLists.txt").is_file() and (_REPO_ROOT / "native").is_dir():
    if _NATIVE_SRC_STAGE.exists():
        shutil.rmtree(_NATIVE_SRC_STAGE)
    (_NATIVE_SRC_STAGE / "native").mkdir(parents=True, exist_ok=True)
    shutil.copy2(_REPO_ROOT / "CMakeLists.txt", _NATIVE_SRC_STAGE / "CMakeLists.txt")
    for _nf in ("nrlmsis21_c_api.F90", "nrlmsis21_c_api.h", "nrlmsis21_jni.c"):
        shutil.copy2(_REPO_ROOT / "native" / _nf, _NATIVE_SRC_STAGE / "native" / _nf)


class BinaryBdistWheel(_bdist_wheel):
    """Tags binary wheels ``py3-none-<platform>`` or wrapper-only wheels ``py3-none-any``."""

    def get_tag(self):
        python, abi, plat = super().get_tag()
        python, abi = "py3", "none"
        if WRAPPER_ONLY:
            return python, abi, "any"
        if sys.platform == "win32":
            plat = "win_amd64"
        elif sys.platform.startswith("linux"):
            plat = "linux_x86_64"
        return python, abi, plat


LICENSE_PATTERNS = ["nrlmsis2.1_license.txt", "LICENSE*"]

if WRAPPER_ONLY:
    # Public source-wrapper distribution: exclude compiled native binaries, legacy 1.0 JAR, and msis21.parm
    package_patterns = [
        "lib/orekit-nrlmsis21-1.0.2.jar",
        "_native_src/CMakeLists.txt",
        "_native_src/native/*",
    ] + LICENSE_PATTERNS
    exclude_patterns = ["lib/*.dll", "lib/*.so*", "lib/*.parm", "lib/orekit-nrlmsis21-1.0.jar"]
elif sys.platform == "win32":
    package_patterns = ["lib/*.dll", "lib/orekit-nrlmsis21-1.0.2.jar", "lib/*.parm"] + LICENSE_PATTERNS
    exclude_patterns = ["lib/*.so*", "lib/orekit-nrlmsis21-1.0.jar"]
elif sys.platform.startswith("linux"):
    package_patterns = ["lib/*.so*", "lib/orekit-nrlmsis21-1.0.2.jar", "lib/*.parm"] + LICENSE_PATTERNS
    exclude_patterns = ["lib/*.dll", "lib/orekit-nrlmsis21-1.0.jar"]
else:
    package_patterns = ["lib/orekit-nrlmsis21-1.0.2.jar"] + LICENSE_PATTERNS
    exclude_patterns = ["lib/orekit-nrlmsis21-1.0.jar"]

setup(
    package_data={"orekit_nrlmsis21": package_patterns},
    exclude_package_data={"orekit_nrlmsis21": exclude_patterns},
    include_package_data=False,
    options=BUILD_OPTIONS,
    cmdclass={"bdist_wheel": BinaryBdistWheel},
)
