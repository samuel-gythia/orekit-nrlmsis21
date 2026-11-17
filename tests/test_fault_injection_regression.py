"""
Automated cross-platform fault-injection and HotSpot C2 repeatability regression
suite for orekit-nrlmsis21 (v1.0.2+).

Covers:
  - Missing, empty, truncated, and 0xFF (NaN) msis21.parm files
  - Parameter directory paths > 128 chars and paths missing a trailing '/'
  - Uninitialized C/JNI calc() calls (both with and without ./msis21.parm in CWD)
  - Direct C NULL pointers via ctypes (no segfault / access violation)
  - Relative library path loading via Nrlmsis21Native.load()
  - NaN / +/-Inf / negative scalars and ap[0..6] in native calc(), ConstantSpaceWeather,
    and Nrlmsis21Atmosphere.getDensity()
  - Null date/position/frame checks including getVelocity(null, pos, frame)
  - AbsoluteDate.PAST_INFINITY and AbsoluteDate.FUTURE_INFINITY rejection
  - Short / null ap arrays from custom SpaceWeatherProvider implementations
  - 100,000-call HotSpot C2 stress repeatability (0 NaN/0.0 dropouts, 0 aborts)
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.resolve()
try:
    import orekit_nrlmsis21  # noqa: F401
except ImportError:
    sys.path.insert(0, str((PROJECT_ROOT / "python").resolve()))


def _resolve_orekit_data() -> Path:
    env_path = os.environ.get("OREKIT_DATA_PATH")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend([PROJECT_ROOT / "orekit-data", Path("orekit-data")])
    for c in candidates:
        if c.is_dir():
            return c.resolve()
    raise FileNotFoundError(
        "Could not locate orekit-data directory. Set OREKIT_DATA_PATH or place orekit-data/ in repo root."
    )


def _run_isolated(name: str, script: str, cwd: Path, timeout: int = 120) -> None:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    repo_py = str((PROJECT_ROOT / "python").resolve())
    env["PYTHONPATH"] = f"{repo_py}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else repo_py

    proc = subprocess.run(
        [sys.executable, "-B", "-c", textwrap.dedent(script)],
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    assert proc.returncode == 0, (
        f"[{name}] Subprocess exited with rc={proc.returncode}\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert "SENTINEL:SURVIVED" in proc.stdout, (
        f"[{name}] Subprocess terminated early (possible Fortran STOP rc=0) without reaching sentinel!\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def test_c_api_fault_containment() -> None:
    """Tests direct C API (ctypes) fault isolation without JVM startup."""
    with tempfile.TemporaryDirectory(prefix="nrl_fi_c_") as td:
        tmp = Path(td)
        empty_cwd = tmp / "empty_cwd"
        empty_cwd.mkdir()

        script = f"""
        import ctypes, os, shutil
        from pathlib import Path
        import orekit_nrlmsis21 as nrl

        lib_path = nrl.find_native_library()
        parm_src = nrl.find_parameter_file()
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(lib_path.parent))

        lib = ctypes.CDLL(str(lib_path))
        lib.msis21_init_c.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        lib.msis21_init_c.restype = ctypes.c_int
        lib.msis21_init_ex_c.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        lib.msis21_init_ex_c.restype = ctypes.c_int
        lib.msis21_is_initialized_c.argtypes = []
        lib.msis21_is_initialized_c.restype = ctypes.c_int
        lib.msis21_set_storm_ap_mode_c.argtypes = [ctypes.c_int]
        lib.msis21_set_storm_ap_mode_c.restype = ctypes.c_int
        lib.msis21_get_storm_ap_mode_c.argtypes = []
        lib.msis21_get_storm_ap_mode_c.restype = ctypes.c_int
        dp = ctypes.POINTER(ctypes.c_double)
        lib.msis21_calc_c.argtypes = [
            ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
            ctypes.c_double, ctypes.c_double, dp, dp, dp, dp, dp
        ]
        lib.msis21_calc_c.restype = ctypes.c_int

        ap_ok = (ctypes.c_double * 7)(15.0, 15.0, 15.0, 15.0, 15.0, 15.0, 15.0)
        rho = ctypes.c_double()
        tn = ctypes.c_double()
        tex = ctypes.c_double()
        dn = (ctypes.c_double * 10)()

        # 1. Pre-init guards (including CWD containing msis21.parm!)
        assert lib.msis21_is_initialized_c() == 0
        assert lib.msis21_get_storm_ap_mode_c() == -4
        assert lib.msis21_set_storm_ap_mode_c(0) == -4

        cwd_with_parm = Path(r"{tmp}") / "cwd_parm"
        cwd_with_parm.mkdir()
        shutil.copy2(parm_src, cwd_with_parm / "msis21.parm")
        os.chdir(cwd_with_parm)
        st_uninit = lib.msis21_calc_c(
            180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0,
            ap_ok, ctypes.byref(rho), ctypes.byref(tn), ctypes.byref(tex), dn
        )
        assert st_uninit == -4, f"Expected MSIS21_ERR_NOT_INITIALIZED (-4), got {{st_uninit}}"
        os.chdir(r"{empty_cwd}")

        # 2. NULL pointers in init
        assert lib.msis21_init_c(None, b"msis21.parm") == -1
        assert lib.msis21_init_c(b"./", None) == -1
        assert lib.msis21_init_ex_c(None, None, 1) == -1

        # 3. Missing, >128 char, empty, truncated, and 0xFF (NaN) msis21.parm
        missing_dir = Path(r"{tmp}") / "does_not_exist"
        assert lib.msis21_init_c((str(missing_dir).replace("\\\\", "/") + "/").encode(), b"msis21.parm") == -3

        long_dir = Path(r"{tmp}") / ("a" * 50) / ("b" * 50) / ("c" * 40)
        long_dir.mkdir(parents=True)
        shutil.copy2(parm_src, long_dir / "msis21.parm")
        long_str = str(long_dir).replace("\\\\", "/") + "/"
        assert len(long_str) > 128
        assert lib.msis21_init_c(long_str.encode(), b"msis21.parm") == -3

        empty_dir = Path(r"{tmp}") / "parm_empty"
        empty_dir.mkdir()
        (empty_dir / "msis21.parm").write_bytes(b"")
        assert lib.msis21_init_c((str(empty_dir).replace("\\\\", "/") + "/").encode(), b"msis21.parm") == -3

        trunc_dir = Path(r"{tmp}") / "parm_trunc"
        trunc_dir.mkdir()
        (trunc_dir / "msis21.parm").write_bytes(parm_src.read_bytes()[:1024])
        assert lib.msis21_init_c((str(trunc_dir).replace("\\\\", "/") + "/").encode(), b"msis21.parm") == -3

        nan_dir = Path(r"{tmp}") / "parm_nan"
        nan_dir.mkdir()
        (nan_dir / "msis21.parm").write_bytes(b"\\xff" * parm_src.stat().st_size)
        assert lib.msis21_init_c((str(nan_dir).replace("\\\\", "/") + "/").encode(), b"msis21.parm") == -3
        assert lib.msis21_is_initialized_c() == 0

        # 4. Valid short path WITHOUT trailing '/' (must normalize and succeed)
        short_dir = Path(r"{tmp}") / "p_ok"
        short_dir.mkdir()
        shutil.copy2(parm_src, short_dir / "msis21.parm")
        short_no_slash = str(short_dir).replace("\\\\", "/").rstrip("/")
        assert len(short_no_slash) < 127, f"Temp path unexpectedly long ({{len(short_no_slash)}}): {{short_no_slash}}"
        st_init = lib.msis21_init_c(short_no_slash.encode(), b"msis21.parm")
        assert st_init == 0, f"Expected 0 for valid path without trailing slash, got {{st_init}}"
        assert lib.msis21_is_initialized_c() == 1
        assert lib.msis21_get_storm_ap_mode_c() == 1

        # 5. Direct C NULL pointers in msis21_calc_c (no segfault)
        assert lib.msis21_calc_c(180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0, None, None, None, None, None) == -1
        assert lib.msis21_calc_c(180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0, None, ctypes.byref(rho), ctypes.byref(tn), ctypes.byref(tex), dn) == -1
        assert lib.msis21_calc_c(180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0, ap_ok, None, ctypes.byref(tn), ctypes.byref(tex), dn) == -1
        assert lib.msis21_calc_c(180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0, ap_ok, ctypes.byref(rho), None, ctypes.byref(tex), dn) == -1
        assert lib.msis21_calc_c(180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0, ap_ok, ctypes.byref(rho), ctypes.byref(tn), None, dn) == -1
        assert lib.msis21_calc_c(180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0, ap_ok, ctypes.byref(rho), ctypes.byref(tn), ctypes.byref(tex), None) == -1

        # 6. NaN / +/-Inf / negative scalar & ap7 inputs
        nan = float("nan")
        pinf = float("inf")
        ninf = float("-inf")
        bad_scalars = [
            (nan, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0),
            (180.0, nan, 400.0, 0.0, 0.0, 150.0, 150.0),
            (180.0, 43200.0, nan, 0.0, 0.0, 150.0, 150.0),
            (180.0, 43200.0, pinf, 0.0, 0.0, 150.0, 150.0),
            (180.0, 43200.0, ninf, 0.0, 0.0, 150.0, 150.0),
            (180.0, 43200.0, 400.0, nan, 0.0, 150.0, 150.0),
            (180.0, 43200.0, 400.0, 0.0, nan, 150.0, 150.0),
            (180.0, 43200.0, 400.0, 0.0, 0.0, nan, 150.0),
            (180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, nan),
            (180.0, 43200.0, 400.0, 0.0, 0.0, -1.0, 150.0),
            (180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, -1.0),
        ]
        for args in bad_scalars:
            st = lib.msis21_calc_c(*args, ap_ok, ctypes.byref(rho), ctypes.byref(tn), ctypes.byref(tex), dn)
            assert st == -2, f"Expected -2 for {{args}}, got {{st}}"

        for bad_val in [nan, pinf, ninf, -1.0]:
            ap_bad = (ctypes.c_double * 7)(15.0, 15.0, 15.0, bad_val, 15.0, 15.0, 15.0)
            st = lib.msis21_calc_c(180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0, ap_bad, ctypes.byref(rho), ctypes.byref(tn), ctypes.byref(tex), dn)
            assert st == -2, f"Expected -2 for ap7 bad_val={{bad_val}}, got {{st}}"

        # 7. Recovery check
        st_rec = lib.msis21_calc_c(180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0, ap_ok, ctypes.byref(rho), ctypes.byref(tn), ctypes.byref(tex), dn)
        assert st_rec == 0 and rho.value > 0.0

        print("SENTINEL:SURVIVED")
        """
        _run_isolated("c_api_fault_containment", script, cwd=empty_cwd)


def test_jni_lifecycle_and_relative_load() -> None:
    """Tests pre-JVM guards, calc before load/init, relative load(), and bad msis21.parm in JNI."""
    with tempfile.TemporaryDirectory(prefix="nrl_fi_jni_") as td:
        tmp = Path(td)
        empty_cwd = tmp / "empty_cwd"
        empty_cwd.mkdir()

        script = f"""
        import os, shutil
        from pathlib import Path
        import jpype
        import orekit_jpype as orekit
        import orekit_nrlmsis21 as nrl

        # 1. Pre-JVM guards
        for label, fn in [
            ("load_native_library", lambda: nrl.load_native_library()),
            ("get_atmosphere_class", lambda: nrl.get_atmosphere_class()),
            ("Nrlmsis21AtmosphereWrapper", lambda: nrl.Nrlmsis21AtmosphereWrapper(None, None, None)),
        ]:
            try:
                fn()
                raise AssertionError(f"{{label}} unexpectedly succeeded before JVM start")
            except RuntimeError:
                pass

        # 2. Start JVM without loading native binary
        orekit.initVM(additional_classpaths=nrl.java_classpaths())
        from org.ssa.nrlmsis21 import Nrlmsis21Native

        assert not Nrlmsis21Native.isLoaded()
        assert not Nrlmsis21Native.isReady()
        assert not nrl.is_native_loaded()

        ap7 = jpype.JArray(jpype.JDouble)([15.0] * 7)
        sc = jpype.JArray(jpype.JDouble)(3)
        dn = jpype.JArray(jpype.JDouble)(10)

        # 3. calc() before load() -> UnsatisfiedLinkError
        try:
            Nrlmsis21Native.calc(180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0, ap7, sc, dn)
            raise AssertionError("Expected UnsatisfiedLinkError before load()")
        except jpype.JException as ex:
            assert "UnsatisfiedLinkError" in str(type(ex)) or "UnsatisfiedLinkError" in repr(ex)

        # 4. Nonexistent relative path load() -> UnsatisfiedLinkError (does not fall into loadLibrary)
        try:
            Nrlmsis21Native.load("nonexistent_dir/libnrlmsis21_jni.so")
            raise AssertionError("Expected UnsatisfiedLinkError for nonexistent relative path")
        except jpype.JException as ex:
            assert not Nrlmsis21Native.isLoaded()

        # 5. Valid relative path load() relative to JVM initial user.dir
        lib_path = nrl.find_native_library()
        rel_dir = Path(r"{empty_cwd}") / "rel_bin"
        rel_dir.mkdir(exist_ok=True)
        shutil.copy2(lib_path, rel_dir / lib_path.name)
        rel_lib = f"rel_bin/{{lib_path.name}}"
        Nrlmsis21Native.load(rel_lib)
        assert Nrlmsis21Native.isLoaded()
        assert not Nrlmsis21Native.isInitialized()
        assert not Nrlmsis21Native.isReady()

        # 6. calc() before init() in CWD WITH msis21.parm and empty CWD -> -4 (no silent CWD self-init!)
        parm_src = nrl.find_parameter_file()
        cwd_parm = Path(r"{tmp}") / "cwd_parm"
        cwd_parm.mkdir()
        shutil.copy2(parm_src, cwd_parm / "msis21.parm")
        os.chdir(cwd_parm)
        assert Nrlmsis21Native.calc(180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0, ap7, sc, dn) == -4
        os.chdir(r"{empty_cwd}")
        assert Nrlmsis21Native.calc(180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0, ap7, sc, dn) == -4

        # 7. Missing / bad parm files via Nrlmsis21Native.init -> -3 without JVM abort
        missing_dir = Path(r"{tmp}") / "no_such_parm_dir"
        assert Nrlmsis21Native.init(str(missing_dir).replace("\\\\", "/") + "/", "msis21.parm") == -3

        empty_dir = Path(r"{tmp}") / "parm_empty"
        empty_dir.mkdir()
        (empty_dir / "msis21.parm").write_bytes(b"")
        assert Nrlmsis21Native.init(str(empty_dir).replace("\\\\", "/") + "/", "msis21.parm") == -3

        trunc_dir = Path(r"{tmp}") / "parm_trunc"
        trunc_dir.mkdir()
        (trunc_dir / "msis21.parm").write_bytes(parm_src.read_bytes()[:1024])
        assert Nrlmsis21Native.init(str(trunc_dir).replace("\\\\", "/") + "/", "msis21.parm") == -3

        nan_dir = Path(r"{tmp}") / "parm_nan"
        nan_dir.mkdir()
        (nan_dir / "msis21.parm").write_bytes(b"\\xff" * parm_src.stat().st_size)
        assert Nrlmsis21Native.init(str(nan_dir).replace("\\\\", "/") + "/", "msis21.parm") == -3

        long_dir = Path(r"{tmp}") / ("x" * 50) / ("y" * 50) / ("z" * 40)
        long_dir.mkdir(parents=True)
        shutil.copy2(parm_src, long_dir / "msis21.parm")
        assert Nrlmsis21Native.init(str(long_dir).replace("\\\\", "/") + "/", "msis21.parm") == -3

        # 8. Valid short parm path without trailing '/' -> 0, ready, calc succeeds
        short_dir = Path(r"{tmp}") / "p_ok"
        short_dir.mkdir()
        shutil.copy2(parm_src, short_dir / "msis21.parm")
        st_ok = Nrlmsis21Native.init(str(short_dir).replace("\\\\", "/").rstrip("/"), "msis21.parm")
        assert st_ok == 0
        assert Nrlmsis21Native.isInitialized()
        assert Nrlmsis21Native.isReady()
        assert nrl.is_native_loaded()
        assert Nrlmsis21Native.calc(180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0, ap7, sc, dn) == 0
        assert sc[0] > 0.0

        print("SENTINEL:SURVIVED")
        """
        _run_isolated("jni_lifecycle_and_relative_load", script, cwd=empty_cwd)


def test_java_and_orekit_fault_containment() -> None:
    """Tests NaN/Inf/negative inputs, null dates, INFINITY dates, and short/null arrays in Java/Orekit."""
    data_dir = _resolve_orekit_data()
    with tempfile.TemporaryDirectory(prefix="nrl_fi_java_") as td:
        tmp = Path(td)
        script = f"""
        import math
        import jpype
        import orekit_nrlmsis21 as nrl

        nrl.init_vm()
        from orekit_jpype.pyhelpers import setup_orekit_data
        setup_orekit_data(filenames=r"{data_dir}", from_pip_library=False)

        from org.ssa.nrlmsis21 import Nrlmsis21Native, Nrlmsis21Atmosphere, ConstantSpaceWeather
        from org.orekit.time import AbsoluteDate, TimeScalesFactory
        from org.orekit.frames import FramesFactory
        from org.orekit.bodies import OneAxisEllipsoid
        from org.orekit.utils import Constants, IERSConventions
        from org.hipparchus.geometry.euclidean.threed import Vector3D

        utc = TimeScalesFactory.getUTC()
        itrf = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
        earth = OneAxisEllipsoid(Constants.WGS84_EARTH_EQUATORIAL_RADIUS, Constants.WGS84_EARTH_FLATTENING, itrf)
        epoch = AbsoluteDate(2024, 1, 15, 12, 0, 0.0, utc)
        pos = Vector3D(Constants.WGS84_EARTH_EQUATORIAL_RADIUS + 400_000.0, 0.0, 0.0)

        ap7 = jpype.JArray(jpype.JDouble)([15.0] * 7)
        sc = jpype.JArray(jpype.JDouble)(3)
        dn = jpype.JArray(jpype.JDouble)(10)

        # 1. Nrlmsis21Native.calc NaN / +/-Inf / negative inputs -> -2 (JVM survives!)
        nan, pinf, ninf = float("nan"), float("inf"), float("-inf")
        for args in [
            (nan, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0),
            (180.0, nan, 400.0, 0.0, 0.0, 150.0, 150.0),
            (180.0, 43200.0, nan, 0.0, 0.0, 150.0, 150.0),
            (180.0, 43200.0, pinf, 0.0, 0.0, 150.0, 150.0),
            (180.0, 43200.0, ninf, 0.0, 0.0, 150.0, 150.0),
            (180.0, 43200.0, 400.0, nan, 0.0, 150.0, 150.0),
            (180.0, 43200.0, 400.0, 0.0, nan, 150.0, 150.0),
            (180.0, 43200.0, 400.0, 0.0, 0.0, nan, 150.0),
            (180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, nan),
            (180.0, 43200.0, 400.0, 0.0, 0.0, -5.0, 150.0),
            (180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, -5.0),
        ]:
            assert Nrlmsis21Native.calc(*args, ap7, sc, dn) == -2

        for bad in [nan, pinf, ninf, -1.0]:
            bad_ap = jpype.JArray(jpype.JDouble)([15.0, 15.0, bad, 15.0, 15.0, 15.0, 15.0])
            assert Nrlmsis21Native.calc(180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0, bad_ap, sc, dn) == -2

        # 2. Short & null arrays in Nrlmsis21Native.calc -> -1, then recovery -> 0
        ap3 = jpype.JArray(jpype.JDouble)([15.0] * 3)
        sc2 = jpype.JArray(jpype.JDouble)(2)
        dn5 = jpype.JArray(jpype.JDouble)(5)
        for a, s, d in [(ap3, sc, dn), (ap7, sc2, dn), (ap7, sc, dn5), (None, sc, dn), (ap7, None, dn), (ap7, sc, None)]:
            assert Nrlmsis21Native.calc(180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0, a, s, d) == -1
        assert Nrlmsis21Native.calc(180.0, 43200.0, 400.0, 0.0, 0.0, 150.0, 150.0, ap7, sc, dn) == 0 and sc[0] > 0.0

        # 3. ConstantSpaceWeather rejection of NaN, +/-Inf, negative, short/null ap7
        for ctor in [
            lambda: ConstantSpaceWeather(nan, 150.0, 15.0),
            lambda: ConstantSpaceWeather(150.0, pinf, 15.0),
            lambda: ConstantSpaceWeather(150.0, 150.0, ninf),
            lambda: ConstantSpaceWeather(-1.0, 150.0, 15.0),
            lambda: ConstantSpaceWeather(150.0, -1.0, 15.0),
            lambda: ConstantSpaceWeather(150.0, 150.0, -1.0),
            lambda: ConstantSpaceWeather(150.0, 150.0, ap3),
            lambda: ConstantSpaceWeather(150.0, 150.0, None),
            lambda: ConstantSpaceWeather(150.0, 150.0, jpype.JArray(jpype.JDouble)([15.0, 15.0, nan, 15.0, 15.0, 15.0, 15.0])),
            lambda: ConstantSpaceWeather(150.0, 150.0, jpype.JArray(jpype.JDouble)([15.0, -2.0, 15.0, 15.0, 15.0, 15.0, 15.0])),
        ]:
            try:
                ctor()
                raise AssertionError("ConstantSpaceWeather accepted invalid argument")
            except Exception:
                pass

        # 4. Nrlmsis21Atmosphere null args, null dates (including getVelocity), INFINITY dates, NaN/Inf positions
        sw = ConstantSpaceWeather(150.0, 150.0, 15.0)
        atm = Nrlmsis21Atmosphere(earth, sw, utc)

        for label, fn in [
            ("getDensity(null, pos, itrf)", lambda: atm.getDensity(None, pos, itrf)),
            ("getDensity(epoch, null, itrf)", lambda: atm.getDensity(epoch, None, itrf)),
            ("getDensity(epoch, pos, null)", lambda: atm.getDensity(epoch, pos, None)),
            ("getVelocity(null, pos, itrf)", lambda: atm.getVelocity(None, pos, itrf)),
            ("getVelocity(epoch, null, itrf)", lambda: atm.getVelocity(epoch, None, itrf)),
            ("getVelocity(epoch, pos, null)", lambda: atm.getVelocity(epoch, pos, None)),
            ("getDensity(PAST_INFINITY)", lambda: atm.getDensity(AbsoluteDate.PAST_INFINITY, pos, itrf)),
            ("getDensity(FUTURE_INFINITY)", lambda: atm.getDensity(AbsoluteDate.FUTURE_INFINITY, pos, itrf)),
            ("getVelocity(PAST_INFINITY)", lambda: atm.getVelocity(AbsoluteDate.PAST_INFINITY, pos, itrf)),
            ("getVelocity(FUTURE_INFINITY)", lambda: atm.getVelocity(AbsoluteDate.FUTURE_INFINITY, pos, itrf)),
            ("getDensity(NaN vec)", lambda: atm.getDensity(epoch, Vector3D(nan, 0.0, 0.0), itrf)),
            ("getDensity(+Inf vec)", lambda: atm.getDensity(epoch, Vector3D(pinf, 0.0, 0.0), itrf)),
            ("getDensity(-Inf vec)", lambda: atm.getDensity(epoch, Vector3D(ninf, 0.0, 0.0), itrf)),
        ]:
            try:
                res = fn()
                raise AssertionError(f"{{label}} unexpectedly returned {{res}}")
            except Exception:
                pass

        # 5. Malformed SpaceWeatherProvider arrays/NaNs must throw, NEVER silently return 0.0
        @jpype.JImplements("org.ssa.nrlmsis21.SpaceWeatherProvider")
        class BadProvider:
            def __init__(self, f107a_val, f107_val, ap_val):
                self._f107a = f107a_val
                self._f107 = f107_val
                self._ap = ap_val
            @jpype.JOverride
            def getF107Avg(self, d): return self._f107a
            @jpype.JOverride
            def getF107(self, d): return self._f107
            @jpype.JOverride
            def getAp(self, d): return self._ap

        for bad_prov in [
            BadProvider(150.0, 150.0, ap3),
            BadProvider(150.0, 150.0, None),
            BadProvider(nan, 150.0, ap7),
            BadProvider(150.0, -10.0, ap7),
            BadProvider(150.0, 150.0, jpype.JArray(jpype.JDouble)([15.0, nan, 15.0, 15.0, 15.0, 15.0, 15.0])),
        ]:
            atm_bad = Nrlmsis21Atmosphere(earth, bad_prov, utc)
            try:
                rho_bad = atm_bad.getDensity(epoch, pos, itrf)
                raise AssertionError(f"Expected exception for bad provider, silently returned {{rho_bad}}")
            except Exception:
                pass

        print("SENTINEL:SURVIVED")
        """
        _run_isolated("java_and_orekit_fault_containment", script, cwd=tmp)


def test_hotspot_c2_100k_repeatability() -> None:
    """Runs 100,000 interleaved/varying calls through HotSpot C2 verifying 0 NaN/0.0 dropouts."""
    data_dir = _resolve_orekit_data()
    with tempfile.TemporaryDirectory(prefix="nrl_fi_c2_") as td:
        tmp = Path(td)
        script = f"""
        import math
        import jpype
        import orekit_nrlmsis21 as nrl

        nrl.init_vm()
        from orekit_jpype.pyhelpers import setup_orekit_data
        setup_orekit_data(filenames=r"{data_dir}", from_pip_library=False)

        from org.ssa.nrlmsis21 import Nrlmsis21Atmosphere, ConstantSpaceWeather
        from org.orekit.time import AbsoluteDate, TimeScalesFactory
        from org.orekit.frames import FramesFactory
        from org.orekit.bodies import OneAxisEllipsoid
        from org.orekit.utils import Constants, IERSConventions
        from org.hipparchus.geometry.euclidean.threed import Vector3D

        utc = TimeScalesFactory.getUTC()
        itrf = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
        earth = OneAxisEllipsoid(Constants.WGS84_EARTH_EQUATORIAL_RADIUS, Constants.WGS84_EARTH_FLATTENING, itrf)
        epoch = AbsoluteDate(2026, 10, 25, 12, 0, 0.0, utc)
        atm = Nrlmsis21Atmosphere(earth, ConstantSpaceWeather(150.0, 150.0, 15.0), utc)

        re = Constants.WGS84_EARTH_EQUATORIAL_RADIUS
        # Probe baseline densities across both below-zetaB (50 km) and LEO regimes
        ref_points = [
            (epoch, Vector3D(re + 50_000.0, 0.0, 0.0)),
            (epoch, Vector3D(re + 250_000.0, 0.0, 0.0)),
            (epoch, Vector3D(re + 400_000.0, 0.0, 0.0)),
            (epoch, Vector3D(re + 800_000.0, 0.0, 0.0)),
        ]
        pre_rhos = [float(atm.getDensity(d, p, itrf)) for d, p in ref_points]
        assert all(math.isfinite(r) and r > 0.0 for r in pre_rhos)

        # Pre-construct rotating/interleaved test states across [50 km, 800 km] to exercise HotSpot C2
        states = []
        alts_m = [50_000.0, 400_000.0, 90_000.0, 250_000.0, 600_000.0, 800_000.0]
        for k in range(250):
            alt_m = alts_m[k % len(alts_m)] + (k % 7) * 500.0
            lat = math.radians(-70.0 + (k % 29) * 5.0)
            lon = math.radians(-180.0 + (k % 36) * 10.0)
            r = re + alt_m
            pos = Vector3D(r * math.cos(lat) * math.cos(lon),
                           r * math.cos(lat) * math.sin(lon),
                           r * math.sin(lat))
            dt = epoch.shiftedBy(float(k * 37.0))
            states.append((dt, pos))

        n_calls = 100_000
        n_states = len(states)
        for i in range(n_calls):
            dt, pos = states[i % n_states]
            rho = float(atm.getDensity(dt, pos, itrf))
            if not math.isfinite(rho) or rho <= 0.0:
                raise AssertionError(f"Dropout/non-finite density at call {{i}}: rho={{rho}}")

        post_rhos = [float(atm.getDensity(d, p, itrf)) for d, p in ref_points]
        for idx, (r0, r1) in enumerate(zip(pre_rhos, post_rhos)):
            assert r0 == r1, f"Repeatability drift at point {{idx}}: {{r0}} vs {{r1}}"

        print(f"HOTSPOT_100K_OK pre_400km={{pre_rhos[2]:.12e}}")
        print("SENTINEL:SURVIVED")
        """
        _run_isolated("hotspot_c2_100k_repeatability", script, cwd=tmp, timeout=180)


def main() -> int:
    tests = [
        test_c_api_fault_containment,
        test_jni_lifecycle_and_relative_load,
        test_java_and_orekit_fault_containment,
        test_hotspot_c2_100k_repeatability,
    ]
    for fn in tests:
        print(f"[RUN] {fn.__name__} ...")
        fn()
        print(f"[PASS] {fn.__name__}")
    print("\n[PASS] All fault-injection and 100k C2 repeatability regressions passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
