"""
One-step local setup CLI for orekit-nrlmsis21 (pymsis-style user-local build).

Acquires or validates user-supplied NRLMSIS 2.1 source files, compiles the
native JNI shared library locally with CMake, and stages the built shared
library and ``msis21.parm`` into ``~/.orekit_nrlmsis21/`` (or a custom directory)
for automatic runtime discovery by ``orekit_nrlmsis21.loader``.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from . import acquire, loader


def default_user_home_dir() -> Path:
    """Returns the default user-local runtime directory (``~/.orekit_nrlmsis21``)."""
    return Path.home() / ".orekit_nrlmsis21"


def find_native_bridge_source_root() -> Path:
    """
    Locates the directory containing ``CMakeLists.txt`` and ``native/``.

    Checks the repository root first (editable/source checkout), then the
    packaged ``orekit_nrlmsis21/_native_src`` directory (wheel installs).
    """
    pkg_dir = Path(__file__).resolve().parent
    repo_root = pkg_dir.parents[1]
    for candidate in (repo_root, pkg_dir / "_native_src"):
        if (candidate / "CMakeLists.txt").is_file() and (candidate / "native" / "nrlmsis21_c_api.F90").is_file():
            return candidate
    raise FileNotFoundError(
        "Could not locate CMakeLists.txt and native/ bridge sources. "
        "Reinstall from the wrapper wheel/sdist or run from a source checkout."
    )


def build_native_library(
    nrlmsis_source_dir: Path,
    install_dir: Optional[Path] = None,
    build_dir: Optional[Path] = None,
    c_compiler: Optional[str] = None,
    fortran_compiler: Optional[str] = None,
) -> Path:
    """
    Configures and builds ``libnrlmsis21_jni`` via CMake against ``nrlmsis_source_dir``
    and stages the compiled shared library + ``msis21.parm`` into ``install_dir``.
    """
    info = acquire.validate_nrlmsis21_directory(nrlmsis_source_dir, require_parm=True, require_license=False)
    bridge_root = find_native_bridge_source_root()

    target_install = (install_dir or default_user_home_dir()).expanduser().resolve()
    target_build = (build_dir or (target_install / "build")).expanduser().resolve()
    target_install.mkdir(parents=True, exist_ok=True)
    target_build.mkdir(parents=True, exist_ok=True)

    cmake_cmd = [
        "cmake",
        "-S", str(bridge_root),
        "-B", str(target_build),
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DNRLMSIS21_SOURCE_DIR={nrlmsis_source_dir.resolve()}",
    ]
    if shutil.which("ninja"):
        cmake_cmd.extend(["-G", "Ninja"])
    if c_compiler:
        cmake_cmd.append(f"-DCMAKE_C_COMPILER={c_compiler}")
    if fortran_compiler:
        cmake_cmd.append(f"-DCMAKE_Fortran_COMPILER={fortran_compiler}")

    subprocess.run(cmake_cmd, check=True)
    subprocess.run(
        ["cmake", "--build", str(target_build), "--target", "nrlmsis21_jni", "--config", "Release"],
        check=True,
    )

    lib_name = loader._get_platform_native_lib_name()
    built = next(iter(target_build.rglob(lib_name)), None)
    if built is None:
        raise FileNotFoundError(f"Compiled native library '{lib_name}' not found under {target_build}")

    staged_lib = target_install / lib_name
    shutil.copy2(built, staged_lib)
    shutil.copy2(info["parm_file"], target_install / "msis21.parm")
    return staged_lib


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="One-step local setup: acquire/verify NRLMSIS 2.1 and compile libnrlmsis21_jni locally."
    )
    src_group = parser.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--download", action="store_true", help="Download NRLMSIS 2.1 from NRL after explicit 'YES' confirmation.")
    src_group.add_argument("--from-archive", type=Path, help="Extract NRLMSIS 2.1 from a local .tar.gz or .zip archive.")
    src_group.add_argument("--source-dir", type=Path, help="Use an existing local NRLMSIS 2.1 directory or cloned mirror.")
    parser.add_argument("--install-dir", type=Path, default=default_user_home_dir(), help="Destination for compiled library & msis21.parm (default: ~/.orekit_nrlmsis21).")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing extracted NRLMSIS 2.1 files.")
    parser.add_argument("--c-compiler", default=None, help="Optional path to C compiler (e.g. C:/msys64/ucrt64/bin/gcc.exe).")
    parser.add_argument("--fortran-compiler", default=None, help="Optional path to Fortran compiler (e.g. C:/msys64/ucrt64/bin/gfortran.exe).")
    args = parser.parse_args(argv)

    install_dir = args.install_dir.expanduser().resolve()
    if args.source_dir is not None:
        nrl_dir = args.source_dir.expanduser().resolve()
    else:
        nrl_dir = install_dir / "nrlmsis21_upstream"
        if args.from_archive is not None:
            acquire.extract_nrlmsis21_archive(args.from_archive, nrl_dir, overwrite=args.overwrite)
        else:
            acquire.download_nrlmsis21_source(nrl_dir, overwrite=args.overwrite)

    staged_lib = build_native_library(
        nrl_dir,
        install_dir=install_dir,
        c_compiler=args.c_compiler,
        fortran_compiler=args.fortran_compiler,
    )
    print("\n[OK] orekit-nrlmsis21 local native setup complete!")
    print(f"  Library : {staged_lib}")
    print(f"  Parm    : {install_dir / 'msis21.parm'}")
    if install_dir == default_user_home_dir().resolve():
        print("  Loader will auto-discover these files without extra environment variables.")
    else:
        print(f"  Set NRLMSIS21_LIB_PATH={staged_lib}")
        print(f"  Set NRLMSIS21_PARM_PATH={install_dir / 'msis21.parm'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
