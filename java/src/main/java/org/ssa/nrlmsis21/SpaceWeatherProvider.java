package org.ssa.nrlmsis21;

import org.orekit.time.AbsoluteDate;
import java.io.Serializable;

/**
 * Provides space-weather indices (F10.7 and 7-element Ap array) for NRLMSIS 2.1.
 *
 * <p>All solar flux and geomagnetic indices must be finite and non-negative. Solar F10.7
 * values follow the NRLMSIS 2.1 convention of observed flux at the actual Sun-Earth
 * distance (not 1-AU adjusted flux), expressed in solar flux units
 * ({@code 1 SFU = 10^-22 W m^-2 Hz^-1}).
 *
 * <p>NRLMSIS 2.1 supports two geomagnetic Ap evaluation modes controlled by native switch
 * {@code sw(9)} (configurable via {@link Nrlmsis21Native#setStormApMode(boolean)}):
 * <ul>
 *   <li><b>Storm-time 7-element Ap history mode ({@code sw(9) = -1.0}, default in v1.0.2):</b>
 *       consumes the full 7-element {@code ap[0..6]} array returned by {@link #getAp(AbsoluteDate)},
 *       incorporating current and historical 3-hour geomagnetic activity indices ({@code ap[1..6]})
 *       alongside the daily index {@code ap[0]}.</li>
 *   <li><b>Daily Ap mode ({@code sw(9) = +1.0}):</b> consumes only the daily geomagnetic index
 *       {@code ap[0]} and ignores {@code ap[1..6]}.</li>
 * </ul>
 */
public interface SpaceWeatherProvider extends Serializable {
    /**
     * 81-day centered average observed F10.7 solar radio flux (SFU).
     *
     * @param date evaluation epoch
     * @return finite, non-negative 81-day centered average observed F10.7 flux [SFU]
     */
    double getF107Avg(AbsoluteDate date);

    /**
     * Daily observed F10.7 solar radio flux for the previous day (SFU).
     *
     * @param date evaluation epoch
     * @return finite, non-negative daily observed F10.7 flux for the previous day [SFU]
     */
    double getF107(AbsoluteDate date);

    /**
     * 7-element geomagnetic activity array {@code Ap}:
     * <ul>
     *   <li>{@code ap[0]} = daily Ap</li>
     *   <li>{@code ap[1]} = 3-hour ap current</li>
     *   <li>{@code ap[2]} = 3-hour ap -3h</li>
     *   <li>{@code ap[3]} = 3-hour ap -6h</li>
     *   <li>{@code ap[4]} = 3-hour ap -9h</li>
     *   <li>{@code ap[5]} = 8-point average ap from -12h to -33h</li>
     *   <li>{@code ap[6]} = 8-point average ap from -36h to -57h</li>
     * </ul>
     *
     * <p>In storm-time Ap history mode ({@code sw(9) = -1.0}, default in v1.0.2), all 7 elements
     * are consumed by NRLMSIS 2.1. In daily Ap mode ({@code sw(9) = +1.0}), only {@code ap[0]}
     * is used and {@code ap[1..6]} are ignored.
     *
     * @param date evaluation epoch
     * @return 7-element array of finite, non-negative Ap values
     */
    double[] getAp(AbsoluteDate date);
}
