package org.ssa.nrlmsis21;

import org.orekit.time.AbsoluteDate;
import java.util.Arrays;

/**
 * Constant space-weather provider for controlled testing and baseline calibration.
 *
 * <p><b>Parameter Order Notice:</b> For backward compatibility with v1.0.0/v1.0.1, the
 * public constructors accept {@code f107Avg} <em>first</em> and daily {@code f107}
 * <em>second</em>: {@code ConstantSpaceWeather(double f107Avg, double f107, ...)}.
 * Callers preferring daily {@code f107} first should use the static factory methods
 * {@link #ofDailyAndAverage(double, double, double)} or
 * {@link #ofDailyAndAverage(double, double, double[])}.
 */
public class ConstantSpaceWeather implements SpaceWeatherProvider {
    private static final long serialVersionUID = 1L;

    private final double f107Avg;
    private final double f107;
    private final double[] ap7;

    /**
     * Constructs a constant space-weather provider from scalar Ap.
     *
     * <p><b>Note parameter order:</b> {@code f107Avg} is first and daily {@code f107} is second.
     * Use {@link #ofDailyAndAverage(double, double, double)} for daily-first ordering.
     *
     * @param f107Avg 81-day centered average F10.7 solar flux [SFU], finite and &ge; 0
     * @param f107 daily F10.7 solar flux [SFU], finite and &ge; 0
     * @param apScalar constant geomagnetic Ap applied to all 7 Ap elements, finite and &ge; 0
     * @throws IllegalArgumentException if any value is non-finite or negative
     */
    public ConstantSpaceWeather(double f107Avg, double f107, double apScalar) {
        this(f107Avg, f107, new double[] { apScalar, apScalar, apScalar, apScalar, apScalar, apScalar, apScalar });
    }

    /**
     * Constructs a constant space-weather provider from a 7-element Ap history array.
     *
     * <p><b>Note parameter order:</b> {@code f107Avg} is first and daily {@code f107} is second.
     * Use {@link #ofDailyAndAverage(double, double, double[])} for daily-first ordering.
     *
     * @param f107Avg 81-day centered average F10.7 solar flux [SFU], finite and &ge; 0
     * @param f107 daily F10.7 solar flux [SFU], finite and &ge; 0
     * @param ap7 7-element geomagnetic Ap array {@code [daily, 0h, -3h, -6h, -9h, -12..-33h, -36..-57h]},
     *            each finite and &ge; 0
     * @throws IllegalArgumentException if {@code ap7} is null, has fewer than 7 elements,
     *                                  or if any value is non-finite or negative
     */
    public ConstantSpaceWeather(double f107Avg, double f107, double[] ap7) {
        if (ap7 == null || ap7.length < 7) {
            throw new IllegalArgumentException("Ap array must contain at least 7 elements.");
        }
        this.f107Avg = validateNonNegativeFinite(f107Avg, "f107Avg");
        this.f107 = validateNonNegativeFinite(f107, "f107");
        for (int i = 0; i < 7; i++) {
            validateNonNegativeFinite(ap7[i], "ap7[" + i + "]");
        }
        this.ap7 = Arrays.copyOf(ap7, 7);
    }

    /**
     * Creates a {@code ConstantSpaceWeather} instance with daily {@code f107} first
     * and 81-day average {@code f107Avg} second.
     *
     * @param f107 daily F10.7 solar flux [SFU], finite and &ge; 0
     * @param f107Avg 81-day centered average F10.7 solar flux [SFU], finite and &ge; 0
     * @param apScalar constant geomagnetic Ap applied to all 7 Ap elements, finite and &ge; 0
     * @return new {@code ConstantSpaceWeather} instance
     * @throws IllegalArgumentException if any value is non-finite or negative
     */
    public static ConstantSpaceWeather ofDailyAndAverage(double f107, double f107Avg, double apScalar) {
        return new ConstantSpaceWeather(f107Avg, f107, apScalar);
    }

    /**
     * Creates a {@code ConstantSpaceWeather} instance with daily {@code f107} first
     * and 81-day average {@code f107Avg} second.
     *
     * @param f107 daily F10.7 solar flux [SFU], finite and &ge; 0
     * @param f107Avg 81-day centered average F10.7 solar flux [SFU], finite and &ge; 0
     * @param ap7 7-element geomagnetic Ap array {@code [daily, 0h, -3h, -6h, -9h, -12..-33h, -36..-57h]},
     *            each finite and &ge; 0
     * @return new {@code ConstantSpaceWeather} instance
     * @throws IllegalArgumentException if {@code ap7} is null, has fewer than 7 elements,
     *                                  or if any value is non-finite or negative
     */
    public static ConstantSpaceWeather ofDailyAndAverage(double f107, double f107Avg, double[] ap7) {
        return new ConstantSpaceWeather(f107Avg, f107, ap7);
    }

    private static double validateNonNegativeFinite(double value, String name) {
        if (!Double.isFinite(value) || value < 0.0) {
            throw new IllegalArgumentException(
                name + " must be finite and non-negative, got: " + value);
        }
        return value;
    }

    @Override
    public double getF107Avg(AbsoluteDate date) {
        return f107Avg;
    }

    @Override
    public double getF107(AbsoluteDate date) {
        return f107;
    }

    @Override
    public double[] getAp(AbsoluteDate date) {
        return Arrays.copyOf(ap7, 7);
    }
}
