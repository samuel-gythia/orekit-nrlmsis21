"""
orekit-nrlmsis21: High-Performance Native NRLMSIS 2.1 Atmosphere Integration for Orekit-JPype.

NRLMSIS(R) 2.1 is distributed under the NRL Open Source Academic Research License Agreement
(NRL-SOF-014-1), which restricts use to non-commercial academic research. See the bundled
``nrlmsis2.1_license.txt``.
"""
from __future__ import annotations

import warnings
from typing import Any

from .loader import (
    java_classpaths,
    load_native_library,
    is_native_loaded,
    find_parameter_file,
    find_native_library,
    _native_class,
)
from .atmosphere import Nrlmsis21AtmosphereWrapper

__version__ = "1.0.2"
__all__ = [
    "init_vm",
    "init_nrlmsis21",
    "java_classpaths",
    "load_native_library",
    "is_native_loaded",
    "find_native_library",
    "find_parameter_file",
    "validate_nrlmsis21_directory",
    "extract_nrlmsis21_archive",
    "download_nrlmsis21_source",
    "set_storm_ap_mode",
    "is_storm_ap_mode",
    "get_atmosphere_class",
    "get_constant_weather_class",
    "create_atmosphere",
    "get_cssi_weather_provider_class",
    "create_cssi_weather_provider",
    "create_constant_weather",
    "Nrlmsis21AtmosphereWrapper",
]


def init_vm(**kwargs: Any) -> Any:
    """
    Initializes the Orekit JVM with orekit-nrlmsis21 JARs and loads the native library.

    If a JVM is already running, the package JAR is registered on its class path dynamically.
    Extra keyword arguments are forwarded to ``orekit_jpype.initVM`` (e.g. ``vmargs``).
    """
    import jpype
    import orekit_jpype as orekit

    cp_list = java_classpaths()

    if jpype.isJVMStarted():
        try:
            from org.ssa.nrlmsis21 import Nrlmsis21Native  # noqa: F401
        except Exception:
            for cp in cp_list:
                jpype.addClassPath(cp)
    else:
        try:
            orekit.initVM(additional_classpaths=cp_list, **kwargs)
        except TypeError:
            orekit.initVM(**kwargs)
            for cp in cp_list:
                jpype.addClassPath(cp)

    load_native_library()
    return orekit


def init_nrlmsis21(*args: Any, **kwargs: Any) -> Any:
    """
    Backward-compatible alias of :func:`init_vm`.

    Earlier milestone scripts called ``init_nrlmsis21(project_root)``. The positional
    ``project_root`` argument is no longer used (binaries and ``msis21.parm`` are discovered
    automatically); passing it emits a :class:`DeprecationWarning` and is otherwise ignored.
    """
    if args:
        warnings.warn(
            "Passing positional arguments (e.g. project_root) to init_nrlmsis21() is deprecated "
            "and ignored; call orekit_nrlmsis21.init_vm() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
    return init_vm(**kwargs)


def set_storm_ap_mode(enabled: bool) -> None:
    """
    Selects how the 7-element ``ap`` array is interpreted by NRLMSIS 2.1.

    Parameters
    ----------
    enabled : bool
        ``True`` (default after initialization): *storm-time* mode -- ``ap[0]`` daily Ap plus the
        six 3-hourly / averaged Ap history bins ``ap[1..6]`` are all used (``switch_legacy(9) = -1``).
        ``False``: *daily Ap* mode -- only ``ap[0]`` is used, ``ap[1..6]`` are ignored
        (``switch_legacy(9) = +1``; matches the legacy NRL test-vector convention).

    Raises
    ------
    RuntimeError
        If the JVM is not running or the native model is not initialized.
    """
    load_native_library()
    Native = _native_class(required=True)
    rc = Native.setStormApMode(bool(enabled))
    if rc is not None and int(rc) != 0:
        raise RuntimeError(f"Nrlmsis21Native.setStormApMode({bool(enabled)}) failed with status {int(rc)}")


def is_storm_ap_mode() -> bool:
    """Returns True if NRLMSIS 2.1 currently uses the 7-element storm-time ``ap`` history."""
    load_native_library()
    return bool(_native_class(required=True).isStormApMode())


def get_atmosphere_class() -> Any:
    """Returns the Java class org.ssa.nrlmsis21.Nrlmsis21Atmosphere."""
    load_native_library()
    from org.ssa.nrlmsis21 import Nrlmsis21Atmosphere
    return Nrlmsis21Atmosphere


def get_constant_weather_class() -> Any:
    """Returns the Java class org.ssa.nrlmsis21.ConstantSpaceWeather."""
    load_native_library()
    from org.ssa.nrlmsis21 import ConstantSpaceWeather
    return ConstantSpaceWeather


def get_cssi_weather_provider_class() -> Any:
    """Returns the Java CSSI-backed NRLMSIS 2.1 weather provider class."""
    load_native_library()
    from org.ssa.nrlmsis21 import CssiWeatherProvider
    return CssiWeatherProvider


def create_cssi_weather_provider(cssi_weather: Any) -> Any:
    """Creates a Java-side SpaceWeatherProvider backed by Orekit CSSI data."""
    ProviderCls = get_cssi_weather_provider_class()
    return ProviderCls(cssi_weather)


def create_atmosphere(earth: Any, space_weather: Any, utc: Any) -> Any:
    AtmCls = get_atmosphere_class()
    return AtmCls(earth, space_weather, utc)


def create_constant_weather(f107: float = 150.0, f107a: float = 150.0, ap: float = 15.0) -> Any:
    """
    Creates a constant space-weather provider.

    Note the Java constructor order is ``(f107Avg, f107, ap)``; this factory takes the arguments
    by *meaning* (``f107`` daily flux, ``f107a`` 81-day average flux, ``ap`` daily Ap) and maps them
    correctly.
    """
    WeatherCls = get_constant_weather_class()
    return WeatherCls(float(f107a), float(f107), float(ap))


def __getattr__(name: str) -> Any:
    if name in ("Nrlmsis21Atmosphere", "Nrlmsis21AtmosphereClass"):
        return get_atmosphere_class()
    if name in ("ConstantSpaceWeather", "ConstantSpaceWeatherClass"):
        return get_constant_weather_class()
    if name == "CssiWeatherProvider":
        return get_cssi_weather_provider_class()
    if name in (
        "validate_nrlmsis21_directory",
        "extract_nrlmsis21_archive",
        "download_nrlmsis21_source",
    ):
        from . import acquire

        return getattr(acquire, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
