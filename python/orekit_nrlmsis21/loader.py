"""
Runtime and native library loader for orekit-nrlmsis21.
Handles platform binary discovery, JVM classpath registration, and model initialization.
"""
from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any, List, Optional, Union

#: Environment variables for user-supplied native binary and parameter file paths.
ENV_LIB_PATH = "NRLMSIS21_LIB_PATH"
ENV_PARM_PATH = "NRLMSIS21_PARM_PATH"
ENV_SOURCE_DIR = "NRLMSIS21_SOURCE_DIR"

#: Exact expected byte size of the upstream NRLMSIS 2.1 parameter file (msis21.parm).
EXPECTED_PARM_BYTES = 536576

#: Preferred JAR file names, newest first. The legacy ``1.0`` name is kept as a fallback only.
_JAR_NAMES = ("orekit-nrlmsis21-1.0.2.jar", "orekit-nrlmsis21-1.0.jar")

#: Fallback readiness flag when running against pre-1.0.2 JAR/native binaries that lack isInitialized().
_NATIVE_INITIALIZED = False


def get_package_lib_dir() -> Path:
    """Returns the internal directory containing bundled distribution binaries."""
    return Path(__file__).resolve().parent / "lib"


def java_classpaths() -> List[str]:
    """
    Returns the absolute paths of all Java JAR dependencies required by orekit-nrlmsis21.

    Pass this to `orekit.initVM(additional_classpaths=...)` when initializing the JVM explicitly.

    Returns
    -------
    list of str
        List containing the absolute path to ``orekit-nrlmsis21-1.0.2.jar`` (falling back to the
        legacy ``orekit-nrlmsis21-1.0.jar`` name if only that exists).
    """
    pkg_lib = get_package_lib_dir()
    dev_target = Path(__file__).resolve().parents[2] / "target"
    searched = []
    for directory in (pkg_lib, dev_target):
        for name in _JAR_NAMES:
            candidate = directory / name
            searched.append(candidate)
            if candidate.exists() and candidate.is_file():
                return [str(candidate.resolve())]
    raise FileNotFoundError(
        "orekit-nrlmsis21 Java JAR not found. Searched:\n"
        + "\n".join(f"  - {p}" for p in searched)
        + "\nCompile the Java adapter via `python build_dev.py --skip-native` or `scripts/build_java.ps1`."
    )


def _get_platform_native_lib_name() -> str:
    """Returns the expected shared library name for the current OS."""
    system = platform.system()
    if system == "Windows":
        return "libnrlmsis21_jni.dll"
    elif system == "Linux":
        return "libnrlmsis21_jni.so"
    else:
        raise OSError(f"Unsupported operating system: {system}. orekit-nrlmsis21 supports Windows x86_64 and Linux x86_64.")


def _alt_platform_native_lib_name() -> str:
    """Returns the unprefixed shared library name for the current OS."""
    return "nrlmsis21_jni.dll" if platform.system() == "Windows" else "nrlmsis21_jni.so"


def _validate_usable_file(path: Path, kind: str, env_var: str) -> Path:
    """Validates that a resolved file exists, is a regular file, and is non-empty."""
    if not path.exists():
        raise FileNotFoundError(
            f"{kind} specified via {env_var} does not exist: '{path}'.\n"
            f"Verify that {env_var} points to a valid file or directory."
        )
    if not path.is_file():
        raise FileNotFoundError(
            f"{kind} specified via {env_var} is not a regular file: '{path}'."
        )
    if path.stat().st_size == 0:
        raise ValueError(
            f"{kind} specified via {env_var} is empty (0 bytes): '{path}'."
        )
    return path.resolve()


def find_native_library(lib_path: Optional[Union[str, os.PathLike]] = None) -> Path:
    """
    Locates the compiled native JNI library for the current platform.

    Resolution order:
    1. Explicit ``lib_path`` argument (if provided).
    2. ``NRLMSIS21_LIB_PATH`` environment variable (file path or directory containing the library).
    3. Package ``lib/`` directory and repository ``build/`` fallback directories.
    """
    lib_name = _get_platform_native_lib_name()
    alt_name = _alt_platform_native_lib_name()

    override_raw = lib_path if lib_path is not None else os.environ.get(ENV_LIB_PATH, "").strip()
    if override_raw:
        source_label = "lib_path argument" if lib_path is not None else f"${ENV_LIB_PATH}"
        override = Path(override_raw).expanduser()
        if override.is_dir():
            for candidate_name in (lib_name, alt_name):
                candidate = override / candidate_name
                if candidate.exists() and candidate.is_file():
                    return _validate_usable_file(candidate, "Native JNI library", source_label)
            raise FileNotFoundError(
                f"Native JNI library ('{lib_name}' or '{alt_name}') not found inside directory "
                f"specified by {source_label}: '{override.resolve()}'."
            )
        return _validate_usable_file(override, "Native JNI library", source_label)

    pkg_lib = get_package_lib_dir()
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        pkg_lib / lib_name,
        pkg_lib / alt_name,
        repo_root / "build" / "milestone2_c" / lib_name,
        repo_root / "build" / "linux" / lib_name,
        repo_root / "build" / lib_name,
    ]
    for c in candidates:
        if c.exists() and c.is_file() and c.stat().st_size > 0:
            return c.resolve()
    raise FileNotFoundError(
        f"Native JNI binary '{lib_name}' not found.\n"
        "Searched locations:\n"
        + "\n".join(f"  - {p}" for p in candidates)
        + "\n\nHow to configure:\n"
        "  1. Obtain the NRLMSIS 2.1 Fortran source code from the U.S. Naval Research Laboratory.\n"
        "  2. Compile the native JNI library locally with CMake:\n"
        "       cmake -S . -B build/milestone2_c -DNRLMSIS21_SOURCE_DIR=/path/to/NRLMSIS2.1 -DCMAKE_BUILD_TYPE=Release\n"
        "       cmake --build build/milestone2_c --target nrlmsis21_jni --config Release\n"
        f"  3. Set the {ENV_LIB_PATH} environment variable to the built '{lib_name}' file (or its directory)."
    )


def find_parameter_file(parm_path: Optional[Union[str, os.PathLike]] = None) -> Path:
    """
    Locates the ``msis21.parm`` parameter table independent of working directory.

    Resolution order:
    1. Explicit ``parm_path`` argument (if provided).
    2. ``NRLMSIS21_PARM_PATH`` environment variable (file path to ``msis21.parm`` or directory containing it).
    3. ``NRLMSIS21_SOURCE_DIR`` environment variable (if it contains ``msis21.parm``).
    4. Package ``lib/msis21.parm`` and repository ``external/NRLMSIS2.1/msis21.parm`` fallbacks.
    """
    override_raw = parm_path if parm_path is not None else os.environ.get(ENV_PARM_PATH, "").strip()
    if override_raw:
        source_label = "parm_path argument" if parm_path is not None else f"${ENV_PARM_PATH}"
        override = Path(override_raw).expanduser()
        if override.is_dir():
            candidate = override / "msis21.parm"
            if not candidate.exists():
                raise FileNotFoundError(
                    f"Parameter file 'msis21.parm' not found inside directory specified by "
                    f"{source_label}: '{override.resolve()}'."
                )
            override = candidate
        resolved = _validate_usable_file(override, "NRLMSIS 2.1 parameter file (msis21.parm)", source_label)
        size = resolved.stat().st_size
        if size != EXPECTED_PARM_BYTES:
            raise ValueError(
                f"Invalid msis21.parm specified via {source_label} ('{resolved}'): "
                f"expected {EXPECTED_PARM_BYTES} bytes, found {size} bytes."
            )
        return resolved

    pkg_lib = get_package_lib_dir()
    repo_root = Path(__file__).resolve().parents[2]
    candidates: List[Path] = []

    src_env = os.environ.get(ENV_SOURCE_DIR, "").strip()
    if src_env:
        candidates.append(Path(src_env).expanduser() / "msis21.parm")

    candidates.extend([
        pkg_lib / "msis21.parm",
        repo_root / "external" / "NRLMSIS2.1" / "msis21.parm",
    ])

    for c in candidates:
        if c.exists() and c.is_file() and c.stat().st_size == EXPECTED_PARM_BYTES:
            return c.resolve()
    raise FileNotFoundError(
        "msis21.parm model parameter table not found.\n"
        "Searched locations:\n"
        + "\n".join(f"  - {p}" for p in candidates)
        + "\n\nHow to configure:\n"
        "  1. Obtain the NRLMSIS 2.1 distribution (including 'msis21.parm') from the U.S. Naval Research Laboratory.\n"
        f"  2. Set the {ENV_PARM_PATH} environment variable to the full path of 'msis21.parm' "
        "(or the directory containing it)."
    )


def _native_class(required: bool = True) -> Any:
    """
    Resolves the Java class ``org.ssa.nrlmsis21.Nrlmsis21Native`` in the running JVM.

    Registers the package JAR on the JPype class loader if it is not yet visible.
    Returns ``None`` when ``required`` is False and the class cannot be resolved.
    """
    import jpype

    if not jpype.isJVMStarted():
        if not required:
            return None
        raise RuntimeError(
            "JVM is not running. Initialize the JVM first via `orekit_nrlmsis21.init_vm()` "
            "or `orekit.initVM(additional_classpaths=orekit_nrlmsis21.java_classpaths())`."
        )

    try:
        from org.ssa.nrlmsis21 import Nrlmsis21Native
        return Nrlmsis21Native
    except Exception:
        pass

    try:
        for cp in java_classpaths():
            jpype.addClassPath(cp)
        from org.ssa.nrlmsis21 import Nrlmsis21Native
        return Nrlmsis21Native
    except Exception as e:
        if not required:
            return None
        raise ImportError(
            "Failed to resolve 'org.ssa.nrlmsis21.Nrlmsis21Native'. Ensure the JAR returned "
            "by `orekit_nrlmsis21.java_classpaths()` was added to the JVM classpath at startup."
        ) from e


def _is_native_ready(Nrlmsis21Native: Any) -> bool:
    """Checks whether the native library is loaded and initialized across 1.0.x and 1.0.2+ JARs."""
    if hasattr(Nrlmsis21Native, "isReady"):
        try:
            return bool(Nrlmsis21Native.isReady())
        except Exception:
            pass
    if hasattr(Nrlmsis21Native, "isLoaded"):
        try:
            return _NATIVE_INITIALIZED and bool(Nrlmsis21Native.isLoaded())
        except Exception:
            pass
    return _NATIVE_INITIALIZED


def load_native_library(
    lib_path: Optional[Union[str, os.PathLike]] = None,
    parm_path: Optional[Union[str, os.PathLike]] = None,
) -> None:
    """
    Loads the native NRLMSIS 2.1 shared library into the active JVM and initializes model tables.

    Safe to call multiple times; subsequent calls are no-ops once the native layer reports ready
    unless an explicit ``parm_path`` override is supplied.
    Requires the JVM to be running and the package JAR to be in the classpath.

    Parameters
    ----------
    lib_path : str or PathLike, optional
        Explicit path to the compiled native JNI library (or directory containing it).
        Defaults to ``$NRLMSIS21_LIB_PATH`` or standard package/build locations.
    parm_path : str or PathLike, optional
        Explicit path to ``msis21.parm`` (or directory containing it).
        Defaults to ``$NRLMSIS21_PARM_PATH``, ``$NRLMSIS21_SOURCE_DIR/msis21.parm``, or fallbacks.

    Raises
    ------
    RuntimeError
        If the JVM is not running, or if ``Nrlmsis21Native.init`` returns a non-zero status.
    """
    global _NATIVE_INITIALIZED
    Nrlmsis21Native = _native_class(required=True)

    if _is_native_ready(Nrlmsis21Native) and lib_path is None and parm_path is None:
        return

    resolved_lib = find_native_library(lib_path=lib_path)
    resolved_parm = find_parameter_file(parm_path=parm_path)

    # Absolute directory formatted with trailing slash for the Fortran runtime
    parm_dir_str = str(resolved_parm.parent.resolve()).replace("\\", "/") + "/"
    parm_file_str = resolved_parm.name

    Nrlmsis21Native.load(str(resolved_lib))
    status = int(Nrlmsis21Native.init(parm_dir_str, parm_file_str))
    if status != 0:
        _NATIVE_INITIALIZED = False
        raise RuntimeError(
            f"Nrlmsis21Native.init failed with status {status} "
            f"(parameter file: {parm_dir_str}{parm_file_str}, native library: {resolved_lib}). "
            "Status codes: -1 null pointer, -2 invalid input, -3 init failed "
            "(missing/short/corrupt msis21.parm or path > 128 chars), -4 not initialized."
        )
    _NATIVE_INITIALIZED = True


def is_native_loaded() -> bool:
    """
    Returns True if the native NRLMSIS 2.1 shared library is loaded *and* initialized.

    Returns False when the JVM has not been started.
    """
    try:
        Nrlmsis21Native = _native_class(required=False)
        if Nrlmsis21Native is None:
            return False
        return _is_native_ready(Nrlmsis21Native)
    except Exception:
        return False
