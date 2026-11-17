package org.ssa.nrlmsis21;

import java.util.Objects;

import org.hipparchus.CalculusFieldElement;
import org.hipparchus.analysis.differentiation.Derivative;
import org.hipparchus.analysis.differentiation.FieldDerivative;
import org.hipparchus.geometry.euclidean.threed.FieldVector3D;
import org.hipparchus.geometry.euclidean.threed.Vector3D;
import org.hipparchus.util.FastMath;
import org.orekit.bodies.GeodeticPoint;
import org.orekit.bodies.OneAxisEllipsoid;
import org.orekit.frames.Frame;
import org.orekit.models.earth.atmosphere.Atmosphere;
import org.orekit.time.AbsoluteDate;
import org.orekit.time.DateTimeComponents;
import org.orekit.time.FieldAbsoluteDate;
import org.orekit.time.TimeScale;

/**
 * NRLMSIS 2.1 empirical neutral atmosphere model for Orekit.
 *
 * <p>Evaluates total mass density in kg/m^3 via native Fortran bindings. Invalid inputs
 * (null arguments, non-finite dates/positions, invalid space weather) and native failures are
 * reported with exceptions; this class never silently returns {@code 0.0} for an error. The only
 * {@code 0.0} result is the documented exosphere cutoff above {@link #getMaxAltitudeKm()}.</p>
 *
 * <p>Native evaluations are serialized by a global lock inside the JNI layer (upstream Fortran
 * keeps mutable global state), so multi-threaded callers in one JVM do not scale.</p>
 */
public class Nrlmsis21Atmosphere implements Atmosphere {

    /** Lower altitude bound (km); lower altitudes are clamped to this value. */
    public static final double MIN_ALTITUDE_KM = 0.0;

    /** Default upper altitude bound (km); density is reported as 0.0 above it. */
    public static final double MAX_ALTITUDE_KM = 1000.0;

    /** Central finite-difference step (m) used for {@code Field} spatial density gradients. */
    private static final double FD_STEP_M = 1.0;

    private final OneAxisEllipsoid earth;
    private final SpaceWeatherProvider spaceWeather;
    private final TimeScale utc;
    private final double maxAltitudeKm;

    public Nrlmsis21Atmosphere(OneAxisEllipsoid earth, SpaceWeatherProvider spaceWeather, TimeScale utc) {
        this(earth, spaceWeather, utc, MAX_ALTITUDE_KM);
    }

    public Nrlmsis21Atmosphere(OneAxisEllipsoid earth, SpaceWeatherProvider spaceWeather, TimeScale utc,
                               double maxAltitudeKm) {
        if (earth == null || spaceWeather == null || utc == null) {
            throw new IllegalArgumentException("Constructor arguments cannot be null.");
        }
        if (!Double.isFinite(maxAltitudeKm) || maxAltitudeKm <= 0.0) {
            throw new IllegalArgumentException(
                "maxAltitudeKm must be finite and > 0 (got " + maxAltitudeKm + ").");
        }
        this.earth = earth;
        this.spaceWeather = spaceWeather;
        this.utc = utc;
        this.maxAltitudeKm = maxAltitudeKm;
    }

    /** @return altitude (km) above which the density is reported as 0.0 */
    public double getMaxAltitudeKm() {
        return maxAltitudeKm;
    }

    @Override
    public Frame getFrame() {
        return earth.getBodyFrame();
    }

    @Override
    public double getDensity(AbsoluteDate date, Vector3D position, Frame frame) {
        Objects.requireNonNull(date, "date cannot be null");
        Objects.requireNonNull(position, "position cannot be null");
        Objects.requireNonNull(frame, "frame cannot be null");
        checkFiniteDate(date);
        checkFinitePosition(position);

        // 1. Transform position to body-fixed geodetic coordinates
        GeodeticPoint gp = earth.transform(position, frame, date);
        double altKm  = gp.getAltitude() * 0.001;
        double latDeg = FastMath.toDegrees(gp.getLatitude());
        double lonDeg = FastMath.toDegrees(gp.getLongitude());
        if (!Double.isFinite(altKm) || !Double.isFinite(latDeg) || !Double.isFinite(lonDeg)) {
            throw new IllegalArgumentException(
                "Non-finite geodetic coordinates (alt=" + altKm + " km, lat=" + latDeg
                    + " deg, lon=" + lonDeg + " deg).");
        }

        // 2. Domain handling: clamp underground, documented cutoff in the exosphere
        if (altKm < MIN_ALTITUDE_KM) {
            altKm = MIN_ALTITUDE_KM;
        } else if (altKm > maxAltitudeKm) {
            return 0.0;
        }

        // 3. Normalize longitude into [-180, 180]
        lonDeg = FastMath.IEEEremainder(lonDeg, 360.0);

        // 4. Day of Year (DOY) and UT-seconds
        DateTimeComponents dtc = date.getComponents(utc);
        double dayOfYear = (double) dtc.getDate().getDayOfYear();
        double utSec     = dtc.getTime().getSecondsInLocalDay();

        // 5. Space-weather parameters (validated before entering native code)
        double f107a = spaceWeather.getF107Avg(date);
        double f107  = spaceWeather.getF107(date);
        double[] ap7 = spaceWeather.getAp(date);
        if (!Double.isFinite(f107a) || f107a < 0.0) {
            throw new IllegalArgumentException("Invalid F10.7 81-day average: " + f107a);
        }
        if (!Double.isFinite(f107) || f107 < 0.0) {
            throw new IllegalArgumentException("Invalid daily F10.7: " + f107);
        }
        if (ap7 == null || ap7.length < 7) {
            throw new IllegalStateException(
                "SpaceWeatherProvider.getAp must return at least 7 elements (got "
                    + (ap7 == null ? "null" : Integer.toString(ap7.length)) + ").");
        }
        for (int i = 0; i < 7; i++) {
            if (!Double.isFinite(ap7[i]) || ap7[i] < 0.0) {
                throw new IllegalArgumentException("Invalid ap[" + i + "]: " + ap7[i]);
            }
        }

        // 6. Native calculation
        double[] scalars = new double[3];
        double[] dn      = new double[10];
        int status = Nrlmsis21Native.calc(dayOfYear, utSec, altKm, latDeg, lonDeg, f107a, f107, ap7, scalars, dn);
        double rho = scalars[0];
        if (status != 0 || !Double.isFinite(rho) || rho < 0.0) {
            throw new IllegalStateException(
                "NRLMSIS 2.1 native calculation failed (status=" + status + ", rho=" + rho + ")");
        }
        return rho;
    }

    @Override
    public Vector3D getVelocity(AbsoluteDate date, Vector3D position, Frame frame) {
        Objects.requireNonNull(date, "date cannot be null");
        Objects.requireNonNull(position, "position cannot be null");
        Objects.requireNonNull(frame, "frame cannot be null");
        checkFiniteDate(date);
        checkFinitePosition(position);
        return Atmosphere.super.getVelocity(date, position, frame);
    }

    /**
     * {@inheritDoc}
     *
     * <p>Spatial derivatives of the density are obtained by central finite differences
     * (step {@value #FD_STEP_M} m in {@code frame}) on the scalar model whenever the field
     * coordinates carry free derivative parameters. Time derivatives are not propagated.</p>
     */
    @Override
    public <T extends CalculusFieldElement<T>> T getDensity(
            FieldAbsoluteDate<T> date, FieldVector3D<T> position, Frame frame) {
        Objects.requireNonNull(date, "date cannot be null");
        Objects.requireNonNull(position, "position cannot be null");
        Objects.requireNonNull(frame, "frame cannot be null");

        final AbsoluteDate d0 = date.toAbsoluteDate();
        final Vector3D p0 = position.toVector3D();
        final double rho0 = getDensity(d0, p0, frame);
        final T zero = date.getField().getZero();

        if (!hasDerivatives(position.getX()) && !hasDerivatives(position.getY())
            && !hasDerivatives(position.getZ())) {
            return zero.add(rho0);
        }

        final double h = FD_STEP_M;
        final double dRhoDx = (getDensity(d0, p0.add(new Vector3D(h, 0, 0)), frame)
                             - getDensity(d0, p0.subtract(new Vector3D(h, 0, 0)), frame)) / (2.0 * h);
        final double dRhoDy = (getDensity(d0, p0.add(new Vector3D(0, h, 0)), frame)
                             - getDensity(d0, p0.subtract(new Vector3D(0, h, 0)), frame)) / (2.0 * h);
        final double dRhoDz = (getDensity(d0, p0.add(new Vector3D(0, 0, h)), frame)
                             - getDensity(d0, p0.subtract(new Vector3D(0, 0, h)), frame)) / (2.0 * h);

        if (rho0 == 0.0 && dRhoDx == 0.0 && dRhoDy == 0.0 && dRhoDz == 0.0) {
            return zero;
        }

        // Deviation from the expansion point carries the derivative structure (value ~ 0)
        final T dx = position.getX().subtract(p0.getX());
        final T dy = position.getY().subtract(p0.getY());
        final T dz = position.getZ().subtract(p0.getZ());
        return dx.multiply(dRhoDx).add(dy.multiply(dRhoDy)).add(dz.multiply(dRhoDz)).add(rho0);
    }

    /**
     * {@inheritDoc}
     *
     * <p>Delegates to Orekit's default implementation (analytical {@code FieldKinematicTransform}),
     * which preserves the exact Earth-rotation (Coriolis) partial derivatives.</p>
     */
    @Override
    public <T extends CalculusFieldElement<T>> FieldVector3D<T> getVelocity(
            FieldAbsoluteDate<T> date, FieldVector3D<T> position, Frame frame) {
        Objects.requireNonNull(date, "date cannot be null");
        Objects.requireNonNull(position, "position cannot be null");
        Objects.requireNonNull(frame, "frame cannot be null");
        return Atmosphere.super.getVelocity(date, position, frame);
    }

    private static boolean hasDerivatives(CalculusFieldElement<?> value) {
        if (value instanceof Derivative<?> d) {
            return d.getFreeParameters() > 0;
        }
        if (value instanceof FieldDerivative<?, ?> fd) {
            return fd.getFreeParameters() > 0;
        }
        // Plain real-valued types carry no derivatives; unknown field types are treated conservatively
        return !(value instanceof org.hipparchus.util.Binary64) && !(value instanceof org.hipparchus.complex.Complex);
    }

    private static void checkFiniteDate(AbsoluteDate date) {
        if (!Double.isFinite(date.durationFrom(AbsoluteDate.J2000_EPOCH))) {
            throw new IllegalArgumentException("Date must be finite (got " + date + ").");
        }
    }

    private static void checkFinitePosition(Vector3D position) {
        if (!Double.isFinite(position.getX()) || !Double.isFinite(position.getY())
            || !Double.isFinite(position.getZ())) {
            throw new IllegalArgumentException("Position must be finite (got " + position + ").");
        }
    }
}
