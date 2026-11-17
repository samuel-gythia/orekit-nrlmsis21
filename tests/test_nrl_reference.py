"""
Regression test: Validates native NRLMSIS 2.1 integration across all 200
official NRL reference vectors (external/NRLMSIS2.1/msis2.1_test_ref_dp.txt),
verifying all 10 density/species outputs, neutral temperature T, and all 388
missing-species sentinel (9.999e-38) entries in legacy daily-Ap mode.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
import numpy as np

project_root = Path(__file__).resolve().parent.parent.resolve()
try:
    import orekit_nrlmsis21  # noqa: F401
except ImportError:
    sys.path.insert(0, str((project_root / "python").resolve()))

import jpype
from orekit_nrlmsis21 import init_vm

DMISSING = 9.999e-38

# Mapping: (ref_col_idx, name, unit, src_kind, src_idx, scale_to_ref)
REF_VARIABLES = [
    (9,  "He",  "cm^-3",  "dn",     4, 1.0e-6),
    (10, "O",   "cm^-3",  "dn",     3, 1.0e-6),
    (11, "N2",  "cm^-3",  "dn",     1, 1.0e-6),
    (12, "O2",  "cm^-3",  "dn",     2, 1.0e-6),
    (13, "Ar",  "cm^-3",  "dn",     6, 1.0e-6),
    (14, "rho", "g/cm^3", "dn",     0, 1.0e-3),
    (15, "H",   "cm^-3",  "dn",     5, 1.0e-6),
    (16, "N",   "cm^-3",  "dn",     7, 1.0e-6),
    (17, "O*",  "cm^-3",  "dn",     8, 1.0e-6),
    (18, "NO",  "cm^-3",  "dn",     9, 1.0e-6),
    (19, "T",   "K",      "scalar", 1, 1.0),
]


def _ensure_initialized() -> None:
    init_vm()


def run_official_200_vector_benchmark() -> int:
    _ensure_initialized()
    from org.ssa.nrlmsis21 import Nrlmsis21Native

    print("==========================================================================")
    print("  NRLMSIS 2.1 OFFICIAL 200-VECTOR REGRESSION BENCHMARK (ALL 11 OUTPUTS)")
    print("==========================================================================")

    ref_file = project_root / "external" / "NRLMSIS2.1" / "msis2.1_test_ref_dp.txt"
    if not ref_file.exists():
        print(f"[FAIL] Reference file not found: {ref_file}")
        return 1

    lines = ref_file.read_text(encoding="latin-1").splitlines()
    data_lines = [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith(("iyd", "#", "!"))
    ]
    assert len(data_lines) == 200, f"Expected 200 reference vectors, found {len(data_lines)}"
    print(f"Loaded {len(data_lines)} reference vectors from msis2.1_test_ref_dp.txt")

    scalars = jpype.JArray(jpype.JDouble)(3)
    dn = jpype.JArray(jpype.JDouble)(10)

    # Toggle daily-Ap mode (sw(9) = +1.0) to match legacy gtd8d reference driver,
    # restoring storm-time Ap history mode (True) in finally.
    prev_storm_mode = Nrlmsis21Native.isStormApMode()
    Nrlmsis21Native.setStormApMode(False)
    assert not Nrlmsis21Native.isStormApMode(), "Failed to disable storm Ap mode"

    try:
        # Verify day-of-year (iyd % 1000) convention against Vector 1
        p0 = data_lines[0].split()
        iyd0, sec0, alt0, lat0, lon0 = (
            float(p0[0]), float(p0[1]), float(p0[2]), float(p0[3]), float(p0[4])
        )
        f107a0, f1070, ap0 = float(p0[6]), float(p0[7]), float(p0[8])
        exp_rho0_kg_m3 = float(p0[14]) * 1000.0
        ap7_test = jpype.JArray(jpype.JDouble)([ap0] * 7)

        st_iyd = Nrlmsis21Native.calc(iyd0, sec0, alt0, lat0, lon0, f107a0, f1070, ap7_test, scalars, dn)
        assert st_iyd == 0
        err_iyd = abs(float(scalars[0]) - exp_rho0_kg_m3)

        st_doy = Nrlmsis21Native.calc(iyd0 % 1000.0, sec0, alt0, lat0, lon0, f107a0, f1070, ap7_test, scalars, dn)
        assert st_doy == 0
        err_doy = abs(float(scalars[0]) - exp_rho0_kg_m3)

        assert err_doy < err_iyd, "Expected doy = iyd % 1000 to match gtd8d convention"
        print(f"Driver Day Mode Verified: doy = iyd % 1000 (initial storm_ap_mode={prev_storm_mode})")

        var_stats = {
            name: {
                "unit": unit,
                "active_rel_errs": [],
                "active_abs_errs": [],
                "sentinels_matched": 0,
                "sentinel_mismatches": 0,
            }
            for _, name, unit, _, _, _ in REF_VARIABLES
        }
        max_scalar_dn0_diff = 0.0

        print("\n--- Sampling Key Atmospheric Regimes ---")
        print(f"{'Alt (km)':>8} | {'Lat':>5} | {'Ref Rho (kg/m3)':>16} | {'Calc Rho (kg/m3)':>16} | {'Rho Rel Err':>12} | {'T Err (K)':>9}")
        print("-" * 78)

        for idx, line in enumerate(data_lines):
            p = line.split()
            assert len(p) >= 20, f"Malformed row {idx + 1}: expected >= 20 columns, got {len(p)}"

            doy = float(int(p[0]) % 1000)
            sec = float(p[1])
            alt = float(p[2])
            lat = float(p[3])
            lon = float(p[4])
            f107a = float(p[6])
            f107 = float(p[7])
            apd = float(p[8])

            ap7 = jpype.JArray(jpype.JDouble)([apd] * 7)
            status = Nrlmsis21Native.calc(doy, sec, alt, lat, lon, f107a, f107, ap7, scalars, dn)
            assert status == 0, f"Calculation failed at vector {idx + 1} with status {status}"

            sc_vals = [float(scalars[i]) for i in range(3)]
            dn_vals = [float(dn[i]) for i in range(10)]
            max_scalar_dn0_diff = max(max_scalar_dn0_diff, abs(sc_vals[0] - dn_vals[0]))

            rho_rel_row = 0.0
            t_abs_row = 0.0

            for col_idx, name, _unit, src_kind, src_idx, scale in REF_VARIABLES:
                ref_val = float(p[col_idx])
                raw_val = dn_vals[src_idx] if src_kind == "dn" else sc_vals[src_idx]

                is_ref_missing = abs(ref_val - DMISSING) / DMISSING < 1.0e-6
                is_calc_missing = abs(raw_val - DMISSING) / DMISSING < 1.0e-12

                st = var_stats[name]
                if is_ref_missing or is_calc_missing:
                    if is_ref_missing and is_calc_missing:
                        st["sentinels_matched"] += 1
                    else:
                        st["sentinel_mismatches"] += 1
                        raise AssertionError(
                            f"Sentinel mismatch at vector {idx + 1} ({name}): "
                            f"ref={ref_val:.6e}, raw={raw_val:.6e}"
                        )
                else:
                    calc_val = raw_val * scale
                    abs_err = abs(calc_val - ref_val)
                    rel_err = abs_err / abs(ref_val) if ref_val != 0.0 else abs_err
                    st["active_abs_errs"].append(abs_err)
                    st["active_rel_errs"].append(rel_err)
                    if name == "rho":
                        rho_rel_row = rel_err
                    elif name == "T":
                        t_abs_row = abs_err

            if idx in (0, 20, 50, 100, 150, 199):
                exp_rho_kg_m3 = float(p[14]) * 1000.0
                print(
                    f"{alt:8.1f} | {lat:5.1f} | {exp_rho_kg_m3:16.5e} | "
                    f"{sc_vals[0]:16.5e} | {rho_rel_row:12.4e} | {t_abs_row:8.4f} K"
                )

        print("\n==========================================================================")
        print("  OFFICIAL BENCHMARK RESULTS (200 VECTORS, ALL 11 OUTPUT QUANTITIES)")
        print("==========================================================================")
        print(f"{'Var':>4} | {'Unit':>6} | {'Active':>6} | {'Sentinels':>9} | {'Max Rel Err':>12} | {'Max Abs Err':>12}")
        print("-" * 68)

        total_sentinels = 0
        total_active = 0
        for _, name, unit, _, _, _ in REF_VARIABLES:
            st = var_stats[name]
            n_act = len(st["active_rel_errs"])
            n_sent = st["sentinels_matched"]
            total_active += n_act
            total_sentinels += n_sent
            max_rel = max(st["active_rel_errs"]) if n_act else 0.0
            max_abs = max(st["active_abs_errs"]) if n_act else 0.0
            print(f"{name:>4} | {unit:>6} | {n_act:6d} | {n_sent:9d} | {max_rel:12.4e} | {max_abs:12.4e}")

            assert st["sentinel_mismatches"] == 0
            if name == "T":
                assert max_abs <= 0.01, f"Temperature max abs err {max_abs:.4f} K exceeded 0.01 K"
            elif name == "rho":
                assert max_rel <= 5.0e-4, f"rho max rel err {max_rel:.4e} exceeded 5.0e-4"
            else:
                assert max_rel <= 5.5e-4, f"{name} max rel err {max_rel:.4e} exceeded 5.5e-4"

        assert total_sentinels == 388, f"Expected 388 missing-species sentinels, matched {total_sentinels}"
        assert total_active == 1812, f"Expected 1812 active values, checked {total_active}"
        assert max_scalar_dn0_diff == 0.0, f"scalars[0] != dn[0]: diff={max_scalar_dn0_diff}"

        print("-" * 68)
        print(f"  Active Values Verified    : {total_active} / 1812")
        print(f"  Missing Sentinels Matched : {total_sentinels} / 388 (9.999e-38)")
        print(f"  Max |scalars[0] - dn[0]|  : {max_scalar_dn0_diff:.1e}")
        print("\n[PASS] Full numerical consistency verified across all 200 vectors, 10 species/rho, T, and 388 sentinels!")
        return 0
    finally:
        Nrlmsis21Native.setStormApMode(True)
        assert Nrlmsis21Native.isStormApMode(), "Failed to restore storm Ap mode to True"


def test_official_200_vector_reference() -> None:
    assert run_official_200_vector_benchmark() == 0


if __name__ == "__main__":
    sys.exit(run_official_200_vector_benchmark())
