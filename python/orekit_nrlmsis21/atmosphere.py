"""
NRLMSIS 2.1 Native Python Module for Orekit-JPype.

Provides high-performance native wrappers around the NRLMSIS 2.1 neutral atmosphere model,
implementing Orekit's Atmosphere interface for high-precision orbit propagation and
Batch Least Squares orbit determination.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .loader import load_native_library

if TYPE_CHECKING:
    from org.orekit.bodies import OneAxisEllipsoid
    from org.orekit.frames import Frame
    from org.orekit.models.earth.atmosphere import Atmosphere
    from org.orekit.time import AbsoluteDate, TimeScale
    from org.hipparchus.geometry.euclidean.threed import Vector3D


class Nrlmsis21AtmosphereWrapper:
    """
    Orekit Atmosphere adapter backed by native NRLMSIS 2.1 Fortran/JNI bindings.

    Evaluates total mass density $\\rho$ [$\\mathrm{kg/m^3}$], neutral temperature $T_n$ [$\\mathrm{K}$],
    and rigid Earth co-rotation velocity $\\mathbf{v}_{\\mathrm{atm}}$ [$\\mathrm{m/s}$] directly inside
    the JVM process space.

    The constructor loads/initializes the native library if necessary and raises a clear
    ``RuntimeError`` if the JVM has not been started (call ``orekit_nrlmsis21.init_vm()`` first).

    Parameters
    ----------
    earth : org.orekit.bodies.OneAxisEllipsoid
        The reference Earth body model (e.g., WGS84) defining geodetic coordinate transformations.
    space_weather : org.ssa.nrlmsis21.SpaceWeatherProvider
        Provider supplying daily $F_{10.7}$, 81-day centered average $F_{10.7a}$, and the 7-element
        geomagnetic $A_p$ array for the queried epoch.
    utc : org.orekit.time.TimeScale
        UTC time scale used to resolve Day of Year (DOY) and UT-seconds of the day.

    Examples
    --------
    >>> from orekit_nrlmsis21 import init_vm, create_atmosphere, create_constant_weather
    >>> init_vm()
    >>> # create_constant_weather(f107, f107a, ap) maps onto the Java constructor
    >>> # ConstantSpaceWeather(f107Avg, f107, ap) for you.
    >>> sw = create_constant_weather(f107=150.0, f107a=150.0, ap=15.0)
    >>> atm = create_atmosphere(earth, sw, utc)
    >>> density = atm.getDensity(epoch, pos_gcrf, gcrf)
    """

    def __init__(
        self,
        earth: "OneAxisEllipsoid",
        space_weather: Any,
        utc: "TimeScale",
    ) -> None:
        load_native_library()
        from org.ssa.nrlmsis21 import Nrlmsis21Atmosphere
        self._java_atm = Nrlmsis21Atmosphere(earth, space_weather, utc)

    @property
    def java_instance(self) -> "Atmosphere":
        """The underlying Java object implementing `org.orekit.models.earth.atmosphere.Atmosphere`."""
        return self._java_atm

    def get_density(self, date: "AbsoluteDate", position: "Vector3D", frame: "Frame") -> float:
        """
        Calculates total atmospheric mass density at a given epoch and position.

        Parameters
        ----------
        date : org.orekit.time.AbsoluteDate
            The epoch of evaluation.
        position : org.hipparchus.geometry.euclidean.threed.Vector3D
            Cartesian position vector in the specified reference frame [meters].
        frame : org.orekit.frames.Frame
            The reference frame in which `position` is expressed (e.g., GCRF, ITRF).

        Returns
        -------
        float
            Total neutral atmospheric density $\\rho$ in $\\mathrm{kg/m^3}$.
        """
        return float(self._java_atm.getDensity(date, position, frame))

    def get_velocity(self, date: "AbsoluteDate", position: "Vector3D", frame: "Frame") -> "Vector3D":
        """
        Calculates atmospheric co-rotation velocity with Earth at a given position.

        Parameters
        ----------
        date : org.orekit.time.AbsoluteDate
            The epoch of evaluation.
        position : org.hipparchus.geometry.euclidean.threed.Vector3D
            Cartesian position vector in the specified reference frame [meters].
        frame : org.orekit.frames.Frame
            The reference frame in which `position` is expressed.

        Returns
        -------
        org.hipparchus.geometry.euclidean.threed.Vector3D
            Atmospheric flow velocity vector in `frame` [$\\mathrm{m/s}$].
        """
        return self._java_atm.getVelocity(date, position, frame)
