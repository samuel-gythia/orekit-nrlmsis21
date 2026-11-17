package org.ssa.nrlmsis21;

import java.util.Objects;
import org.orekit.models.earth.atmosphere.data.CssiSpaceWeatherData;
import org.orekit.time.AbsoluteDate;

/**
 * Java-side Orekit CSSI adapter for the NRLMSIS 2.1 weather interface.
 *
 * <p>Delegates to Orekit's {@link CssiSpaceWeatherData} (using observed solar fluxes and
 * 7-element geomagnetic Ap history) and validates that every returned index is finite
 * and non-negative. Note that {@link #getF107(AbsoluteDate)} queries {@code date - 24h}
 * and {@link #getAp(AbsoluteDate)} queries 3-hour Ap history back to {@code date - 57h},
 * so valid queries near dataset start require {@code date >= getMinDate() + 57h}.
 */
public final class CssiWeatherProvider implements SpaceWeatherProvider {
    private static final long serialVersionUID = 1L;
    private final CssiSpaceWeatherData cssi;

    /**
     * Constructs a CSSI space-weather provider wrapping an Orekit {@link CssiSpaceWeatherData}.
     *
     * @param cssi underlying Orekit CSSI data source
     * @throws NullPointerException if {@code cssi} is null
     */
    public CssiWeatherProvider(CssiSpaceWeatherData cssi) {
        this.cssi = Objects.requireNonNull(cssi, "CssiSpaceWeatherData cannot be null");
    }

    /**
     * Returns the earliest date covered by the underlying CSSI dataset.
     *
     * @return minimum supported epoch
     */
    public AbsoluteDate getMinDate() {
        return cssi.getMinDate();
    }

    /**
     * Returns the latest date covered by the underlying CSSI dataset.
     *
     * @return maximum supported epoch
     */
    public AbsoluteDate getMaxDate() {
        return cssi.getMaxDate();
    }

    @Override
    public double getF107(AbsoluteDate date) {
        Objects.requireNonNull(date, "date cannot be null");
        return validateIndex(cssi.getDailyFlux(date), "F10.7");
    }

    @Override
    public double getF107Avg(AbsoluteDate date) {
        Objects.requireNonNull(date, "date cannot be null");
        return validateIndex(cssi.getAverageFlux(date), "F10.7Avg");
    }

    @Override
    public double[] getAp(AbsoluteDate date) {
        Objects.requireNonNull(date, "date cannot be null");
        double[] ap = cssi.getAp(date);
        if (ap == null || ap.length != 7) {
            throw new IllegalStateException("CSSI must return exactly 7 Ap values.");
        }
        for (int i = 0; i < ap.length; i++) {
            validateIndex(ap[i], "Ap[" + i + "]");
        }
        // CssiSpaceWeatherData.getAp allocates a fresh 7-element double[] on every call.
        return ap;
    }

    private static double validateIndex(double value, String indexName) {
        if (!Double.isFinite(value) || value < 0.0) {
            throw new IllegalStateException(
                "CSSI returned invalid (non-finite or negative) " + indexName + " value: " + value);
        }
        return value;
    }
}

