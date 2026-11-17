"""
Orekit integration tests for the NRLMSIS 2.1 ``Nrlmsis21Atmosphere``.

Covers:
  * altitude density profile / physical sanity / atmosphere velocity (ITRF and GCRF),
  * ``Field`` ``getVelocity`` analytical Earth-rotation (Coriolis) partials vs Orekit ``NRLMSISE00``,
  * ``Field`` ``getDensity`` spatial gradients and ``DragForce(atm, sc, false)`` density gradients,
  * fail-fast behaviour (NaN/Inf positions, +/-infinite dates, invalid space weather, nulls)
    instead of silently returning 0.0,
  * altitude clamping / configurable exosphere cutoff.

Runs under pytest *or* directly (``python tests/test_orekit_atmosphere.py``, exit code 0/1).
Platform independent: the JVM, JAR, JNI library and ``msis21.parm`` are resolved by
``orekit_nrlmsis21.init_vm()``; Orekit data is looked up via ``OREKIT_DATA_PATH`` or ``orekit-data/``.
"""
from __future__ import annotations

import math
import os
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _sanitize_sys_path() -> None:
    """Prefer an installed wheel; fall back to the repo ``python/`` dir.

    The repo root is dropped from ``sys.path`` because ``<root>/java`` (Maven sources) would
    otherwise shadow JPype's ``java.*`` namespace.
    """
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != REPO_ROOT]
    try:
        import orekit_nrlmsis21  # noqa: F401
    except ImportError:
        sys.path.insert(0, str((REPO_ROOT / "python").resolve()))


_sanitize_sys_path()

import orekit_nrlmsis21 as nrl  # noqa: E402

_ENV = None


def _find_orekit_data() -> Path:
    candidates = []
    if os.environ.get("OREKIT_DATA_PATH"):
        candidates.append(Path(os.environ["OREKIT_DATA_PATH"]))
    candidates += [REPO_ROOT / "orekit-data", Path.cwd() / "orekit-data"]
    for c in candidates:
        if c.is_dir():
            return c.resolve()
    raise FileNotFoundError(
        "Orekit data folder not found. Set OREKIT_DATA_PATH or provide "
        + ", ".join(str(c) for c in candidates)
    )


class _Env:
    """Lazily initialised JVM / Orekit objects shared by all tests in this module."""


def env() -> _Env:
    global _ENV
    if _ENV is not None:
        return _ENV

    nrl.init_vm()
    from orekit_jpype.pyhelpers import setup_orekit_data

    setup_orekit_data(filenames=str(_find_orekit_data()), from_pip_library=False)

    from org.hipparchus.geometry.euclidean.threed import Vector3D
    from org.orekit.bodies import OneAxisEllipsoid
    from org.orekit.frames import FramesFactory
    from org.orekit.time import AbsoluteDate, TimeScalesFactory
    from org.orekit.utils import Constants, IERSConventions

    e = _Env()
    e.Vector3D = Vector3D
    e.AbsoluteDate = AbsoluteDate
    e.Constants = Constants
    e.utc = TimeScalesFactory.getUTC()
    e.itrf = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
    e.gcrf = FramesFactory.getGCRF()
    e.earth = OneAxisEllipsoid(Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
                               Constants.WGS84_EARTH_FLATTENING, e.itrf)
    e.sw = nrl.create_constant_weather(150.0, 150.0, 15.0)
    e.atm = nrl.create_atmosphere(e.earth, e.sw, e.utc)
    e.epoch = AbsoluteDate(2026, 10, 25, 12, 0, 0.0, e.utc)
    _ENV = e
    return e


def _equatorial_pos_itrf(e, alt_km: float):
    return e.Vector3D(e.Constants.WGS84_EARTH_EQUATORIAL_RADIUS + alt_km * 1000.0, 0.0, 0.0)


def _pos_gcrf(e, alt_km: float):
    return e.itrf.getTransformTo(e.gcrf, e.epoch).transformPosition(_equatorial_pos_itrf(e, alt_km))


def _expect_raises(exc_types, fn, what: str):
    try:
        result = fn()
    except exc_types:
        return
    except BaseException as ex:  # noqa: BLE001
        raise AssertionError(f"{what}: expected {exc_types}, got {type(ex).__name__}: {ex}") from ex
    raise AssertionError(f"{what}: expected {exc_types} but call returned {result!r}")


# --------------------------------------------------------------------------------------
# Scalar behaviour
# --------------------------------------------------------------------------------------
def test_density_profile():
    e = env()
    altitudes_km = [150.0, 200.0, 300.0, 400.0, 500.0, 600.0, 800.0]
    rho = [float(e.atm.getDensity(e.epoch, _pos_gcrf(e, a), e.gcrf)) for a in altitudes_km]
    print("\n  Alt (km) | rho (kg/m^3)")
    for a, r in zip(altitudes_km, rho):
        print(f"  {a:8.1f} | {r:.5e}")
    assert all(math.isfinite(r) and r > 0.0 for r in rho), rho
    for i in range(len(rho) - 1):
        assert rho[i] > rho[i + 1], f"density not decreasing: {rho[i]} <= {rho[i + 1]}"
    assert 1e-13 < rho[3] < 1e-11, f"density at 400 km ({rho[3]:.3e}) outside physical range"


def test_velocity_scalar():
    e = env()
    pos = _equatorial_pos_itrf(e, 400.0)
    v_itrf = float(e.atm.getVelocity(e.epoch, pos, e.itrf).getNorm())
    v_gcrf = float(e.atm.getVelocity(e.epoch, pos, e.gcrf).getNorm())
    expected = float(e.Constants.WGS84_EARTH_ANGULAR_VELOCITY) * float(pos.getNorm())
    print(f"\n  v_atm ITRF={v_itrf:.3e} m/s, GCRF={v_gcrf:.3f} m/s (omega*r={expected:.3f})")
    assert v_itrf < 1e-6, f"velocity in body-fixed frame must vanish, got {v_itrf}"
    assert abs(v_gcrf - expected) < 5e-3 * expected, (v_gcrf, expected)


def test_altitude_clamp_and_cutoff():
    e = env()
    from org.ssa.nrlmsis21 import Nrlmsis21Atmosphere

    # Underground clamps to sea level
    r0 = float(e.atm.getDensity(e.epoch, _equatorial_pos_itrf(e, 0.0), e.itrf))
    r_under = float(e.atm.getDensity(e.epoch, _equatorial_pos_itrf(e, -10.0), e.itrf))
    assert r0 > 0.0 and r_under == r0, (r0, r_under)

    # Default 1000 km cutoff
    assert float(e.atm.getDensity(e.epoch, _equatorial_pos_itrf(e, 999.0), e.itrf)) > 0.0
    assert float(e.atm.getDensity(e.epoch, _equatorial_pos_itrf(e, 1001.0), e.itrf)) == 0.0

    # Configurable cutoff
    atm500 = Nrlmsis21Atmosphere(e.earth, e.sw, e.utc, 500.0)
    assert float(atm500.getMaxAltitudeKm()) == 500.0
    assert float(atm500.getDensity(e.epoch, _equatorial_pos_itrf(e, 450.0), e.itrf)) > 0.0
    assert float(atm500.getDensity(e.epoch, _equatorial_pos_itrf(e, 550.0), e.itrf)) == 0.0

    from java.lang import IllegalArgumentException
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        _expect_raises(IllegalArgumentException,
                       lambda b=bad: Nrlmsis21Atmosphere(e.earth, e.sw, e.utc, b),
                       f"maxAltitudeKm={bad}")


# --------------------------------------------------------------------------------------
# Fail-fast behaviour (no silent 0.0)
# --------------------------------------------------------------------------------------
def test_invalid_inputs_raise():
    e = env()
    from java.lang import IllegalArgumentException, NullPointerException
    V = e.Vector3D
    r = float(e.Constants.WGS84_EARTH_EQUATORIAL_RADIUS) + 400e3
    nan, inf = float("nan"), float("inf")

    for bad in (V(nan, 0.0, 0.0), V(0.0, nan, r), V(r, 0.0, nan),
                V(inf, 0.0, 0.0), V(-inf, 0.0, 0.0), V(r, inf, 0.0), V(r, 0.0, -inf)):
        _expect_raises(IllegalArgumentException,
                       lambda b=bad: e.atm.getDensity(e.epoch, b, e.itrf), f"getDensity({bad})")
        _expect_raises(IllegalArgumentException,
                       lambda b=bad: e.atm.getVelocity(e.epoch, b, e.gcrf), f"getVelocity({bad})")

    pos = V(r, 0.0, 0.0)
    for name in ("FUTURE_INFINITY", "PAST_INFINITY"):
        bad_date = getattr(e.AbsoluteDate, name)
        _expect_raises(IllegalArgumentException,
                       lambda d=bad_date: e.atm.getDensity(d, pos, e.itrf), f"getDensity({name})")
        _expect_raises(IllegalArgumentException,
                       lambda d=bad_date: e.atm.getVelocity(d, pos, e.itrf), f"getVelocity({name})")

    _expect_raises(NullPointerException, lambda: e.atm.getDensity(None, pos, e.itrf), "null date")
    _expect_raises(NullPointerException, lambda: e.atm.getDensity(e.epoch, None, e.itrf), "null position")
    _expect_raises(NullPointerException, lambda: e.atm.getDensity(e.epoch, pos, None), "null frame")
    _expect_raises(NullPointerException, lambda: e.atm.getVelocity(None, pos, e.itrf), "null date velocity")
    _expect_raises(NullPointerException, lambda: e.atm.getVelocity(e.epoch, None, e.itrf), "null position velocity")
    _expect_raises(NullPointerException, lambda: e.atm.getVelocity(e.epoch, pos, None), "null frame velocity")

    # The model must still work after every rejected call (no poisoned native state)
    assert float(e.atm.getDensity(e.epoch, _pos_gcrf(e, 400.0), e.gcrf)) > 0.0


def _make_weather(f107a=150.0, f107=150.0, ap=None, null_ap=False):
    import jpype
    from jpype import JImplements, JOverride

    @JImplements("org.ssa.nrlmsis21.SpaceWeatherProvider")
    class _Weather:
        @JOverride
        def getF107Avg(self, date):
            return f107a

        @JOverride
        def getF107(self, date):
            return f107

        @JOverride
        def getAp(self, date):
            if null_ap:
                return None
            return jpype.JArray(jpype.JDouble)(ap if ap is not None else [15.0] * 7)

    return _Weather()


def test_invalid_weather_raises():
    e = env()
    from java.lang import IllegalArgumentException, IllegalStateException
    from org.ssa.nrlmsis21 import Nrlmsis21Atmosphere

    pos = _pos_gcrf(e, 400.0)
    nan, inf = float("nan"), float("inf")
    good = [15.0] * 7
    cases = {
        "f107a NaN": (_make_weather(f107a=nan), IllegalArgumentException),
        "f107 NaN": (_make_weather(f107=nan), IllegalArgumentException),
        "f107 Inf": (_make_weather(f107=inf), IllegalArgumentException),
        "f107 negative": (_make_weather(f107=-1.0), IllegalArgumentException),
        "f107a negative": (_make_weather(f107a=-5.0), IllegalArgumentException),
        "ap[3] NaN": (_make_weather(ap=good[:3] + [nan] + good[4:]), IllegalArgumentException),
        "ap[6] Inf": (_make_weather(ap=good[:6] + [inf]), IllegalArgumentException),
        "ap[0] negative": (_make_weather(ap=[-1.0] + good[1:]), IllegalArgumentException),
        "ap short (3)": (_make_weather(ap=[15.0, 15.0, 15.0]), IllegalStateException),
        "ap null": (_make_weather(null_ap=True), IllegalStateException),
    }
    for name, (provider, exc) in cases.items():
        atm = Nrlmsis21Atmosphere(e.earth, provider, e.utc)
        _expect_raises(exc, lambda a=atm: a.getDensity(e.epoch, pos, e.gcrf), name)

    # Recovery: valid provider still works afterwards
    ok = Nrlmsis21Atmosphere(e.earth, _make_weather(), e.utc)
    assert float(ok.getDensity(e.epoch, pos, e.gcrf)) > 0.0


# --------------------------------------------------------------------------------------
# Field (automatic differentiation) contract
# --------------------------------------------------------------------------------------
def _gradient_position(e, pos, nvars=3, offset=0):
    from org.hipparchus.analysis.differentiation import Gradient
    from org.hipparchus.geometry.euclidean.threed import FieldVector3D
    return FieldVector3D(Gradient.variable(nvars, offset + 0, float(pos.getX())),
                         Gradient.variable(nvars, offset + 1, float(pos.getY())),
                         Gradient.variable(nvars, offset + 2, float(pos.getZ())))


def _fd_density_gradient(e, atm, pos, frame, eps=10.0):
    V = e.Vector3D
    grad = []
    for axis in range(3):
        d = [0.0, 0.0, 0.0]
        d[axis] = eps
        plus = V(pos.getX() + d[0], pos.getY() + d[1], pos.getZ() + d[2])
        minus = V(pos.getX() - d[0], pos.getY() - d[1], pos.getZ() - d[2])
        grad.append((float(atm.getDensity(e.epoch, plus, frame))
                     - float(atm.getDensity(e.epoch, minus, frame))) / (2.0 * eps))
    return grad


def test_field_density_gradient():
    e = env()
    from org.hipparchus.analysis.differentiation import GradientField
    from org.orekit.time import FieldAbsoluteDate

    field = GradientField.getField(3)
    pos = _pos_gcrf(e, 400.0)
    f_rho = e.atm.getDensity(FieldAbsoluteDate(field, e.epoch), _gradient_position(e, pos), e.gcrf)
    rho = float(e.atm.getDensity(e.epoch, pos, e.gcrf))
    grad = [float(f_rho.getPartialDerivative(i)) for i in range(3)]
    fd = _fd_density_gradient(e, e.atm, pos, e.gcrf)
    print(f"\n  Field drho/dr={grad}\n  FD    drho/dr={fd}")

    assert float(f_rho.getValue()) == rho
    assert max(abs(g) for g in grad) > 0.0, "Field density gradient is identically zero"
    scale = max(abs(g) for g in fd)
    for g, f in zip(grad, fd):
        assert abs(g - f) <= 1e-2 * scale, (grad, fd)

    # Plain real-valued field (no free parameters) must simply return the value
    from org.hipparchus.util import Binary64Field
    from org.hipparchus.geometry.euclidean.threed import FieldVector3D
    b64 = Binary64Field.getInstance()
    b_rho = e.atm.getDensity(FieldAbsoluteDate(b64, e.epoch), FieldVector3D(b64, pos), e.gcrf)
    assert float(b_rho.getReal()) == rho


def test_field_velocity_coriolis_partials():
    e = env()
    from org.hipparchus.analysis.differentiation import GradientField
    from org.orekit.bodies import CelestialBodyFactory
    from org.orekit.models.earth.atmosphere import NRLMSISE00
    from org.orekit.models.earth.atmosphere.data import CssiSpaceWeatherData
    from org.orekit.time import FieldAbsoluteDate

    field = GradientField.getField(3)
    pos = _pos_gcrf(e, 400.0)
    fdate = FieldAbsoluteDate(field, e.epoch)
    fpos = _gradient_position(e, pos)
    v21 = e.atm.getVelocity(fdate, fpos, e.gcrf)
    jac21 = [[float(c.getPartialDerivative(i)) for i in range(3)] for c in (v21.getX(), v21.getY(), v21.getZ())]

    omega = float(e.Constants.WGS84_EARTH_ANGULAR_VELOCITY)
    frob = math.sqrt(sum(x * x for row in jac21 for x in row))
    print(f"\n  d v_atm/d r (GCRF) Frobenius norm={frob:.6e}, sqrt(2)*omega={math.sqrt(2.0) * omega:.6e}")
    assert frob > 0.0, "Field getVelocity Coriolis partials were dropped"
    assert abs(frob - math.sqrt(2.0) * omega) < 1e-3 * omega
    assert abs(jac21[0][1] + omega) < 1e-3 * omega, jac21   # dvx/dy = -omega
    assert abs(jac21[1][0] - omega) < 1e-3 * omega, jac21   # dvy/dx = +omega

    # Exact agreement with Orekit's own Atmosphere default (NRLMSISE00 does not override it)
    cssi = CssiSpaceWeatherData(CssiSpaceWeatherData.DEFAULT_SUPPORTED_NAMES)
    atm00 = NRLMSISE00(cssi, CelestialBodyFactory.getSun(), e.earth)
    v00 = atm00.getVelocity(fdate, fpos, e.gcrf)
    for c21, c00 in zip((v21.getX(), v21.getY(), v21.getZ()), (v00.getX(), v00.getY(), v00.getZ())):
        assert abs(float(c21.getValue()) - float(c00.getValue())) < 1e-9
        for i in range(3):
            assert abs(float(c21.getPartialDerivative(i)) - float(c00.getPartialDerivative(i))) < 1e-15


def _field_state(e, state, nvars=6):
    """Gradient-valued state (x, y, z, vx, vy, vz) as Orekit's STM machinery builds it."""
    from org.hipparchus.analysis.differentiation import Gradient, GradientField
    from org.hipparchus.geometry.euclidean.threed import FieldVector3D
    from org.orekit.orbits import FieldCartesianOrbit
    from org.orekit.propagation import FieldSpacecraftState
    from org.orekit.time import FieldAbsoluteDate
    from org.orekit.utils import TimeStampedFieldPVCoordinates

    gf = GradientField.getField(nvars)
    pv = state.getPVCoordinates()
    p, v = pv.getPosition(), pv.getVelocity()
    fp = FieldVector3D(Gradient.variable(nvars, 0, p.getX()), Gradient.variable(nvars, 1, p.getY()),
                       Gradient.variable(nvars, 2, p.getZ()))
    fv = FieldVector3D(Gradient.variable(nvars, 3, v.getX()), Gradient.variable(nvars, 4, v.getY()),
                       Gradient.variable(nvars, 5, v.getZ()))
    fdate = FieldAbsoluteDate(gf, state.getDate())
    forb = FieldCartesianOrbit(TimeStampedFieldPVCoordinates(fdate, fp, fv, FieldVector3D.getZero(gf)),
                               state.getFrame(), gf.getZero().add(float(e.Constants.WGS84_EARTH_MU)))
    return gf, FieldSpacecraftState(forb, gf.getZero().add(float(state.getMass())))


def test_dragforce_without_finite_differences_has_density_gradient():
    e = env()
    from org.hipparchus.geometry.euclidean.threed import Vector3D
    from org.orekit.forces.drag import DragForce, IsotropicDrag
    from org.orekit.orbits import CartesianOrbit, KeplerianOrbit, PositionAngleType
    from org.orekit.propagation import SpacecraftState
    from org.orekit.utils import PVCoordinates

    mu = float(e.Constants.WGS84_EARTH_MU)
    a0 = float(e.Constants.WGS84_EARTH_EQUATORIAL_RADIUS) + 400e3
    orbit = KeplerianOrbit(a0, 0.001, math.radians(51.6), 0.0, 0.0, 0.0,
                           PositionAngleType.TRUE, e.gcrf, e.epoch, mu)
    state = SpacecraftState(orbit, 500.0)
    sc = IsotropicDrag(2.0, 2.2)
    force = DragForce(e.atm, sc, False)          # useFiniteDifferencesOnDensityWrtPosition = false

    gf, fstate = _field_state(e, state)
    facc = force.acceleration(fstate, force.getParameters(gf))
    acc_norm = facc.getNorm()
    grad = [float(acc_norm.getPartialDerivative(i)) for i in range(3)]
    print(f"\n  |acc| = {float(acc_norm.getValue()):.6e} m/s^2, d|acc|/dr = {grad}")
    assert float(acc_norm.getValue()) > 0.0
    assert max(abs(g) for g in grad) > 0.0, "DragForce(atm, sc, false) has zero spatial gradient"

    # Compare against central finite differences of the scalar acceleration norm
    pv = state.getPVCoordinates()
    params = force.getParameters(state.getDate())

    def scalar_norm(dp):
        o = CartesianOrbit(PVCoordinates(pv.getPosition().add(dp), pv.getVelocity()), e.gcrf, e.epoch, mu)
        return float(force.acceleration(SpacecraftState(o, 500.0), params).getNorm())

    eps = 10.0
    fd = []
    for axis in range(3):
        d = [0.0, 0.0, 0.0]
        d[axis] = eps
        fd.append((scalar_norm(Vector3D(*d)) - scalar_norm(Vector3D(*[-x for x in d]))) / (2.0 * eps))
    print(f"  FD d|acc|/dr = {fd}")
    scale = max(abs(g) for g in fd)
    for g, f in zip(grad, fd):
        assert abs(g - f) <= 2e-2 * scale, (grad, fd)


# --------------------------------------------------------------------------------------
def _run_all() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"[PASS] {name}")
        except BaseException:  # noqa: BLE001
            failed += 1
            print(f"[FAIL] {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
