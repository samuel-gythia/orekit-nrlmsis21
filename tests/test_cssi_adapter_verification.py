"""
Verification test suite for CssiWeatherProvider, ConstantSpaceWeather,
SpaceWeatherProvider storm/daily Ap modes, and pymsis 2.1 parity.
"""
import datetime as dt
import math
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _import_package():
    try:
        import orekit_nrlmsis21 as nrl
    except ModuleNotFoundError:
        sys.path.insert(0, str(REPO_ROOT / "python"))
        import orekit_nrlmsis21 as nrl
    return nrl


def resolve_orekit_data_dir() -> Path:
    """Resolve orekit-data directory via OREKIT_DATA_PATH or repository layout."""
    candidates = []
    env_path = os.environ.get("OREKIT_DATA_PATH")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path.cwd() / "orekit-data")
    candidates.append(REPO_ROOT / "orekit-data")

    for candidate in candidates:
        if candidate.exists() and (candidate / "CSSI-Space-Weather-Data").exists():
            return candidate.resolve()
    raise AssertionError(
        "Could not find orekit-data with CSSI-Space-Weather-Data. "
        "Set OREKIT_DATA_PATH or place orekit-data at the repository root."
    )


def _to_absolute_date(epoch_dt: dt.datetime, utc, AbsoluteDate):
    return AbsoluteDate(
        epoch_dt.year,
        epoch_dt.month,
        epoch_dt.day,
        epoch_dt.hour,
        epoch_dt.minute,
        float(epoch_dt.second),
        utc,
    )


def _format_cssi_row(
    year: int,
    month: int,
    day: int,
    ap_bins,
    ap_avg,
    f107_obs,
    ctr81_obs,
) -> str:
    """Build a valid 130-character fixed-width CSSI SpaceWeather v1.2 record."""
    # Columns per Orekit CssiSpaceWeatherDataLoader:
    # [0..10] date, [11..46] bartels/kp/sum, [47+4i..50+4i] ap3(8), [79..82] ap_avg,
    # [93..98] f107_adj, [101..106] ctr81_adj, [113..118] f107_obs, [119..124] ctr81_obs
    def _fmt_ap(val):
        if isinstance(val, str):
            return f"{val:>3s}"
        return f"{val:3d}" if isinstance(val, int) else f"{val:3.0f}"

    def _fmt_flux(val):
        if isinstance(val, str):
            return f"{val:>5s}"
        return f"{val:5.1f}"

    ap_part = " ".join(_fmt_ap(v) for v in ap_bins)
    ap_avg_s = _fmt_ap(ap_avg)
    f107_s = _fmt_flux(f107_obs)
    ctr81_s = _fmt_flux(ctr81_obs)
    line = (
        f"{year:04d} {month:02d} {day:02d} 2593 19"
        f" 10 10 10 10 10 10 10 10  80"
        f" {ap_part} {ap_avg_s} 0.1 0 100 {f107_s} 0"
        f" {ctr81_s} 150.0 {f107_s} {ctr81_s} 150.0"
    )
    return line


def run_verification() -> int:
    print(f"=== Verification of orekit-nrlmsis21 on {sys.platform} (Python {sys.version.split()[0]}) ===")

    nrl = _import_package()
    print(f"[1] Package version: {nrl.__version__}")
    assert nrl.__version__ == "1.0.2", f"Expected version 1.0.2, got {nrl.__version__}"

    nrl.init_vm()
    print(f"[2] JVM started and native library loaded: {nrl.is_native_loaded()}")
    assert nrl.is_native_loaded(), "Expected native library to be loaded after init_vm()"

    from orekit_jpype.pyhelpers import setup_orekit_data

    data_dir = resolve_orekit_data_dir()
    setup_orekit_data(filenames=str(data_dir), from_pip_library=False)
    print(f"[3] Orekit data loaded from {data_dir}")

    import jpype
    from java.lang import IllegalArgumentException, IllegalStateException, NullPointerException
    from org.hipparchus.geometry.euclidean.threed import Vector3D
    from org.orekit.bodies import OneAxisEllipsoid
    from org.orekit.data import DataSource
    from org.orekit.frames import FramesFactory
    from org.orekit.models.earth.atmosphere.data import CssiSpaceWeatherData
    from org.orekit.time import AbsoluteDate, TimeScalesFactory
    from org.orekit.utils import Constants, IERSConventions
    from org.ssa.nrlmsis21 import (
        ConstantSpaceWeather,
        CssiWeatherProvider,
        Nrlmsis21Atmosphere,
        Nrlmsis21Native,
    )

    # 4. Java Class Loading & Date Bounds
    CssiCls = nrl.get_cssi_weather_provider_class()
    assert CssiCls is CssiWeatherProvider, f"Class mismatch: {CssiCls} != {CssiWeatherProvider}"
    print(f"[4] get_cssi_weather_provider_class() loaded: {CssiCls.__name__}")

    cssi_data = CssiSpaceWeatherData(CssiSpaceWeatherData.DEFAULT_SUPPORTED_NAMES)
    provider = nrl.create_cssi_weather_provider(cssi_data)
    assert provider is not None
    assert provider.getMinDate().equals(cssi_data.getMinDate()), "getMinDate() mismatch"
    assert provider.getMaxDate().equals(cssi_data.getMaxDate()), "getMaxDate() mismatch"
    print(f"[5] CssiWeatherProvider instantiated; range = [{provider.getMinDate()}, {provider.getMaxDate()}]")

    utc = TimeScalesFactory.getUTC()
    itrf = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
    earth = OneAxisEllipsoid(
        Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
        Constants.WGS84_EARTH_FLATTENING,
        itrf,
    )

    # 6. Quiet, Moderate, and Geomagnetic Storm Epochs
    epoch_specs = [
        ("Quiet Solar Min 2008", dt.datetime(2008, 1, 15, 6, 30, 0, tzinfo=dt.timezone.utc)),
        ("Quiet 2020", dt.datetime(2020, 6, 21, 0, 0, 0, tzinfo=dt.timezone.utc)),
        ("Moderate Cycle 24", dt.datetime(2014, 4, 11, 18, 0, 0, tzinfo=dt.timezone.utc)),
        ("Halloween Storm 2003", dt.datetime(2003, 10, 29, 7, 30, 0, tzinfo=dt.timezone.utc)),
        ("Gannon Storm 2024 Peak", dt.datetime(2024, 5, 11, 1, 30, 0, tzinfo=dt.timezone.utc)),
        ("Gannon Storm 2024 Post", dt.datetime(2024, 5, 12, 6, 0, 0, tzinfo=dt.timezone.utc)),
    ]

    print("\n--- [6] Verifying CSSI Input Equality & ConstantSpaceWeather Parameter Order ---")
    for label, epoch_dt in epoch_specs:
        epoch = _to_absolute_date(epoch_dt, utc, AbsoluteDate)
        f107_direct = float(cssi_data.getDailyFlux(epoch))
        f107_prov = float(provider.getF107(epoch))
        assert f107_direct == f107_prov, f"F10.7 mismatch at {label}: {f107_direct} != {f107_prov}"

        f107a_direct = float(cssi_data.getAverageFlux(epoch))
        f107a_prov = float(provider.getF107Avg(epoch))
        assert f107a_direct == f107a_prov, f"F10.7a mismatch at {label}: {f107a_direct} != {f107a_prov}"

        ap_direct = list(cssi_data.getAp(epoch))
        ap_prov = list(provider.getAp(epoch))
        assert len(ap_prov) == 7, f"Expected 7 Ap values, got {len(ap_prov)}"
        for idx, (a_d, a_p) in enumerate(zip(ap_direct, ap_prov)):
            assert a_d == a_p, f"Ap[{idx}] mismatch at {label}: {a_d} != {a_p}"

        print(
            f"  {label:24s} ({epoch.toString()[:19]}): "
            f"F107={f107_prov:.1f}, F107a={f107a_prov:.1f}, Ap={[round(v, 1) for v in ap_prov]}"
        )

    # Verify ConstantSpaceWeather constructor (f107Avg, f107, ...) vs ofDailyAndAverage(f107, f107Avg, ...)
    sample_epoch = _to_absolute_date(epoch_specs[0][1], utc, AbsoluteDate)
    sw_ctor = ConstantSpaceWeather(140.0, 210.0, 25.0)
    sw_factory_scalar = ConstantSpaceWeather.ofDailyAndAverage(210.0, 140.0, 25.0)
    sw_factory_arr = ConstantSpaceWeather.ofDailyAndAverage(
        210.0, 140.0, jpype.JArray(jpype.JDouble)([25.0] * 7)
    )
    for sw_obj in (sw_ctor, sw_factory_scalar, sw_factory_arr):
        assert float(sw_obj.getF107Avg(sample_epoch)) == 140.0
        assert float(sw_obj.getF107(sample_epoch)) == 210.0
        assert list(sw_obj.getAp(sample_epoch)) == [25.0] * 7

    print("\n--- [7] Verifying Atmosphere Density Equivalence (CSSI vs ConstantSpaceWeather) ---")
    atm_cssi = nrl.create_atmosphere(earth, provider, utc)
    altitudes_km = [150.0, 250.0, 400.0, 600.0]

    for label, epoch_dt in epoch_specs:
        epoch = _to_absolute_date(epoch_dt, utc, AbsoluteDate)
        f107 = provider.getF107(epoch)
        f107a = provider.getF107Avg(epoch)
        ap7 = provider.getAp(epoch)

        sw_const = ConstantSpaceWeather(f107a, f107, ap7)
        sw_const_factory = ConstantSpaceWeather.ofDailyAndAverage(f107, f107a, ap7)
        atm_const = Nrlmsis21Atmosphere(earth, sw_const, utc)
        atm_factory = Nrlmsis21Atmosphere(earth, sw_const_factory, utc)

        for alt in altitudes_km:
            r = Constants.WGS84_EARTH_EQUATORIAL_RADIUS + alt * 1000.0
            pos = Vector3D(r, 0.0, 0.0)
            rho_cssi = float(atm_cssi.getDensity(epoch, pos, itrf))
            rho_const = float(atm_const.getDensity(epoch, pos, itrf))
            rho_factory = float(atm_factory.getDensity(epoch, pos, itrf))

            assert rho_cssi > 0.0, f"Non-positive density: {rho_cssi}"
            assert math.isclose(rho_cssi, rho_const, rel_tol=1e-15, abs_tol=0.0)
            assert math.isclose(rho_cssi, rho_factory, rel_tol=1e-15, abs_tol=0.0)

        print(f"  {label:24s}: exact CSSI == ConstantSpaceWeather == ofDailyAndAverage across 150..600 km")

    print("\n--- [8] Verifying Null, NaN, Inf, and Negative Input Validation ---")
    # 8a. Null checks on CssiWeatherProvider (specific NullPointerException assertions)
    for call_name, fn in [
        ("CssiWeatherProvider(None)", lambda: CssiWeatherProvider(None)),
        ("provider.getF107(None)", lambda: provider.getF107(None)),
        ("provider.getF107Avg(None)", lambda: provider.getF107Avg(None)),
        ("provider.getAp(None)", lambda: provider.getAp(None)),
    ]:
        try:
            fn()
            raise AssertionError(f"{call_name} should have thrown NullPointerException")
        except NullPointerException:
            print(f"  {call_name} -> NullPointerException (PASS)")

    # 8b. ConstantSpaceWeather validation (NaN, Inf, negative, null/short array)
    valid_ap = jpype.JArray(jpype.JDouble)([15.0] * 7)
    bad_ap_nan = jpype.JArray(jpype.JDouble)([15.0, 15.0, float("nan"), 15.0, 15.0, 15.0, 15.0])
    bad_ap_neg = jpype.JArray(jpype.JDouble)([15.0, 15.0, 15.0, -1.0, 15.0, 15.0, 15.0])
    short_ap = jpype.JArray(jpype.JDouble)([15.0] * 6)

    for desc, fn in [
        ("ConstantSpaceWeather(NaN, 150, 15)", lambda: ConstantSpaceWeather(float("nan"), 150.0, 15.0)),
        ("ConstantSpaceWeather(150, Inf, 15)", lambda: ConstantSpaceWeather(150.0, float("inf"), 15.0)),
        ("ConstantSpaceWeather(150, 150, -Inf)", lambda: ConstantSpaceWeather(150.0, 150.0, float("-inf"))),
        ("ConstantSpaceWeather(-1, 150, 15)", lambda: ConstantSpaceWeather(-1.0, 150.0, 15.0)),
        ("ConstantSpaceWeather(150, -0.1, 15)", lambda: ConstantSpaceWeather(150.0, -0.1, 15.0)),
        ("ConstantSpaceWeather(150, 150, -5)", lambda: ConstantSpaceWeather(150.0, 150.0, -5.0)),
        ("ConstantSpaceWeather(150, 150, bad_ap_nan)", lambda: ConstantSpaceWeather(150.0, 150.0, bad_ap_nan)),
        ("ConstantSpaceWeather(150, 150, bad_ap_neg)", lambda: ConstantSpaceWeather(150.0, 150.0, bad_ap_neg)),
        ("ConstantSpaceWeather(150, 150, None)", lambda: ConstantSpaceWeather(150.0, 150.0, None)),
        ("ConstantSpaceWeather(150, 150, short_ap)", lambda: ConstantSpaceWeather(150.0, 150.0, short_ap)),
        ("ofDailyAndAverage(-1, 150, valid_ap)", lambda: ConstantSpaceWeather.ofDailyAndAverage(-1.0, 150.0, valid_ap)),
    ]:
        try:
            fn()
            raise AssertionError(f"{desc} should have thrown IllegalArgumentException")
        except IllegalArgumentException:
            pass
    print("  ConstantSpaceWeather NaN/Inf/negative/short-array rejections -> IllegalArgumentException (PASS)")

    # 8c. Synthetic CSSI DataSource with NaN and negative fluxes / Ap
    with tempfile.TemporaryDirectory() as tmpdir:
        rows = [
            "DATATYPE CssiSpaceWeather",
            "VERSION 1.2",
            "NUM_OBSERVED_POINTS 5",
            "BEGIN OBSERVED",
            _format_cssi_row(2024, 1, 1, [4, 4, 4, 4, 4, 4, 4, 4], 4, 150.0, 150.0),
            _format_cssi_row(2024, 1, 2, [4, 4, 4, 4, 4, 4, 4, 4], 4, "NaN", 150.0),
            _format_cssi_row(2024, 1, 3, [4, 4, 4, 4, 4, 4, 4, "NaN"], 4, -10.0, "NaN"),
            _format_cssi_row(2024, 1, 4, [4, 4, 4, 4, 4, 4, 4, 4], -5, 150.0, -20.0),
            _format_cssi_row(2024, 1, 5, [4, 4, 4, 4, 4, 4, 4, 4], 4, 150.0, 150.0),
            "END OBSERVED",
            "BEGIN DAILY_PREDICTED",
            "END DAILY_PREDICTED",
            "BEGIN MONTHLY_FIT",
            "END MONTHLY_FIT",
        ]
        bad_cssi_path = Path(tmpdir) / "bad_cssi.txt"
        bad_cssi_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

        bad_cssi = CssiSpaceWeatherData(DataSource(str(bad_cssi_path)))
        bad_prov = CssiWeatherProvider(bad_cssi)

        d_nan = AbsoluteDate(2024, 1, 3, 22, 0, 0.0, utc)  # prev day f107=NaN, curr ctr81=NaN, curr bin7 Ap=NaN
        d_neg = AbsoluteDate(2024, 1, 4, 12, 0, 0.0, utc)  # prev day f107=-10.0, curr ctr81=-20.0, curr apAvg=-5

        for label, call in [
            ("bad_prov.getF107(NaN)", lambda: bad_prov.getF107(d_nan)),
            ("bad_prov.getF107Avg(NaN)", lambda: bad_prov.getF107Avg(d_nan)),
            ("bad_prov.getAp(NaN)", lambda: bad_prov.getAp(d_nan)),
            ("bad_prov.getF107(neg)", lambda: bad_prov.getF107(d_neg)),
            ("bad_prov.getF107Avg(neg)", lambda: bad_prov.getF107Avg(d_neg)),
            ("bad_prov.getAp(neg)", lambda: bad_prov.getAp(d_neg)),
        ]:
            try:
                call()
                raise AssertionError(f"{label} should have thrown IllegalStateException")
            except IllegalStateException:
                pass
    print("  CssiWeatherProvider NaN and negative flux/Ap rejections -> IllegalStateException (PASS)")

    print("\n--- [9] Phase C: Storm Ap History Mode vs Daily Ap Mode & pymsis Parity ---")
    assert Nrlmsis21Native.isStormApMode() is True, "Default v1.0.2 mode must be storm-time Ap mode"
    assert nrl.is_storm_ap_mode() is True, "Python is_storm_ap_mode() must match native default"

    try:
        import pymsis
        has_pymsis = True
    except ImportError:
        has_pymsis = False
        print("  [SKIP] pymsis not installed in this environment; skipping external pymsis parity cross-check.")

    pos_400_itrf = Vector3D(Constants.WGS84_EARTH_EQUATORIAL_RADIUS + 400_000.0, 0.0, 0.0)
    scalars_q = jpype.JArray(jpype.JDouble)(3)
    dn_q = jpype.JArray(jpype.JDouble)(10)
    scalars_s = jpype.JArray(jpype.JDouble)(3)
    dn_s = jpype.JArray(jpype.JDouble)(10)
    ap_quiet = jpype.JArray(jpype.JDouble)([15.0, 15.0, 15.0, 15.0, 15.0, 15.0, 15.0])
    ap_storm = jpype.JArray(jpype.JDouble)([15.0, 400.0, 400.0, 400.0, 400.0, 400.0, 400.0])

    try:
        # 9a. Storm Ap History mode (sw(9) = -1.0)
        nrl.set_storm_ap_mode(True)
        assert Nrlmsis21Native.isStormApMode() is True

        status_q = Nrlmsis21Native.calc(302.0, 27000.0, 400.0, 0.0, 0.0, 150.0, 150.0, ap_quiet, scalars_q, dn_q)
        status_s = Nrlmsis21Native.calc(302.0, 27000.0, 400.0, 0.0, 0.0, 150.0, 150.0, ap_storm, scalars_s, dn_s)
        assert status_q == 0 and status_s == 0
        rho_q_storm_mode = float(scalars_q[0])
        rho_s_storm_mode = float(scalars_s[0])
        rel_ap_delta = abs(rho_s_storm_mode - rho_q_storm_mode) / rho_q_storm_mode
        assert rel_ap_delta > 0.10, f"Expected significant ap[1..6] sensitivity in storm mode, got {rel_ap_delta:.3e}"
        print(
            f"  Controlled ap[1..6] Storm Mode: [15..15]={rho_q_storm_mode:.6e}, "
            f"[15,400..400]={rho_s_storm_mode:.6e} (rel delta={rel_ap_delta:.2%}) -> PASS"
        )

        # 9b. Daily Ap mode (sw(9) = +1.0)
        nrl.set_storm_ap_mode(False)
        assert Nrlmsis21Native.isStormApMode() is False
        assert nrl.is_storm_ap_mode() is False

        status_q_d = Nrlmsis21Native.calc(302.0, 27000.0, 400.0, 0.0, 0.0, 150.0, 150.0, ap_quiet, scalars_q, dn_q)
        status_s_d = Nrlmsis21Native.calc(302.0, 27000.0, 400.0, 0.0, 0.0, 150.0, 150.0, ap_storm, scalars_s, dn_s)
        assert status_q_d == 0 and status_s_d == 0
        rho_q_daily_mode = float(scalars_q[0])
        rho_s_daily_mode = float(scalars_s[0])
        assert rho_q_daily_mode == rho_s_daily_mode, (
            f"Daily Ap mode must ignore ap[1..6]: {rho_q_daily_mode} != {rho_s_daily_mode}"
        )
        print(f"  Controlled ap[1..6] Daily Mode: [15..15] == [15,400..400] == {rho_q_daily_mode:.6e} -> PASS")

        if has_pymsis:
            # pymsis expects UTC datetime (use naive UTC to avoid numpy tz deprecation warnings)
            test_dt = dt.datetime(2003, 10, 29, 7, 30, 0)
            py_q_storm = float(
                pymsis.calculate(
                    test_dt, 0.0, 0.0, 400.0, 150.0, 150.0, [[15.0] * 7],
                    version=2.1, geomagnetic_activity=-1,
                ).squeeze()[0]
            )
            py_s_storm = float(
                pymsis.calculate(
                    test_dt, 0.0, 0.0, 400.0, 150.0, 150.0, [[15.0] + [400.0] * 6],
                    version=2.1, geomagnetic_activity=-1,
                ).squeeze()[0]
            )
            py_q_daily = float(
                pymsis.calculate(
                    test_dt, 0.0, 0.0, 400.0, 150.0, 150.0, [[15.0] * 7],
                    version=2.1, geomagnetic_activity=1,
                ).squeeze()[0]
            )
            assert math.isclose(rho_q_storm_mode, py_q_storm, rel_tol=1e-4)
            assert math.isclose(rho_s_storm_mode, py_s_storm, rel_tol=1e-4)
            assert math.isclose(rho_q_daily_mode, py_q_daily, rel_tol=1e-4)
            print("  Controlled ap[1..6] parity vs pymsis.calculate(..., version=2.1) -> PASS (<1e-4 rel)")

        # 9c. Quiet / Moderate / Storm CSSI Epochs across Storm vs Daily Ap Modes
        storm_labels = {"Halloween Storm 2003", "Gannon Storm 2024 Peak", "Gannon Storm 2024 Post"}
        for label, epoch_dt in epoch_specs:
            epoch = _to_absolute_date(epoch_dt, utc, AbsoluteDate)
            f107 = float(provider.getF107(epoch))
            f107a = float(provider.getF107Avg(epoch))
            ap7 = [float(x) for x in provider.getAp(epoch)]

            nrl.set_storm_ap_mode(True)
            rho_storm_mode = float(atm_cssi.getDensity(epoch, pos_400_itrf, itrf))

            nrl.set_storm_ap_mode(False)
            rho_daily_mode = float(atm_cssi.getDensity(epoch, pos_400_itrf, itrf))

            # Daily Ap mode must also match ConstantSpaceWeather(f107a, f107, ap7[0])
            atm_daily_only = Nrlmsis21Atmosphere(earth, ConstantSpaceWeather(f107a, f107, ap7[0]), utc)
            rho_daily_const = float(atm_daily_only.getDensity(epoch, pos_400_itrf, itrf))
            assert math.isclose(rho_daily_mode, rho_daily_const, rel_tol=1e-15, abs_tol=0.0)

            mode_delta_pct = abs(rho_storm_mode - rho_daily_mode) / rho_daily_mode * 100.0
            if label in storm_labels:
                assert mode_delta_pct > 1.0, (
                    f"Expected substantial storm vs daily Ap difference at {label}, got {mode_delta_pct:.4f}%"
                )

            if has_pymsis:
                # Pass geodetic lon/lat/alt matching Orekit's WGS84 transform (equatorial point -> lat=0, lon=0, alt=400 km)
                naive_dt = epoch_dt.replace(tzinfo=None)
                py_storm = float(
                    pymsis.calculate(
                        naive_dt, 0.0, 0.0, 400.0, f107, f107a, [ap7],
                        version=2.1, geomagnetic_activity=-1,
                    ).squeeze()[0]
                )
                py_daily = float(
                    pymsis.calculate(
                        naive_dt, 0.0, 0.0, 400.0, f107, f107a, [ap7],
                        version=2.1, geomagnetic_activity=1,
                    ).squeeze()[0]
                )
                err_storm = abs(rho_storm_mode - py_storm) / py_storm
                err_daily = abs(rho_daily_mode - py_daily) / py_daily
                assert err_storm < 1e-4, f"Storm-mode parity mismatch at {label}: {err_storm:.3e}"
                assert err_daily < 1e-4, f"Daily-mode parity mismatch at {label}: {err_daily:.3e}"
                py_msg = f" | pymsis_err(storm={err_storm:.2e}, daily={err_daily:.2e})"
            else:
                py_msg = ""

            print(
                f"  {label:24s}: storm={rho_storm_mode:.6e}, daily={rho_daily_mode:.6e} "
                f"(delta={mode_delta_pct:.2f}%){py_msg}"
            )
    finally:
        nrl.set_storm_ap_mode(True)

    assert Nrlmsis21Native.isStormApMode() is True, "Must restore default storm Ap mode"

    print("\n=======================================================")
    print("  ALL CSSI & PHASE C VERIFICATION TESTS PASSED!")
    print("=======================================================")
    return 0


def test_cssi_adapter_verification():
    assert run_verification() == 0


if __name__ == "__main__":
    sys.exit(run_verification())
