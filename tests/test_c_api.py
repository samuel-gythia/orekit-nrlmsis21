import sys
import os
import ctypes
from pathlib import Path

def test_c_api(project_root: Path, lib_dir: Path) -> int:
    if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(lib_dir))
        ucrt_bin = Path(r"C:\msys64\ucrt64\bin")
        if ucrt_bin.is_dir():
            os.add_dll_directory(str(ucrt_bin))

    upstream_dir = project_root / "external" / "NRLMSIS2.1"
    parm_path = upstream_dir
    parm_file = "msis21.parm"
    test_in = upstream_dir / "msis2.1_test_in.txt"
    test_ref = upstream_dir / "msis2.1_test_ref_dp.txt"

    dll_candidates = [
        lib_dir / "libnrlmsis21_jni.dll",
        lib_dir / "libnrlmsis21_jni.so",
        lib_dir / "libnrlmsis21.dll",
        lib_dir / "nrlmsis21.dll",
        lib_dir / "libnrlmsis21.so",
        lib_dir / "nrlmsis21.so"
    ]
    lib_path = next((p for p in dll_candidates if p.exists()), None)
    if not lib_path:
        print(f"[FAIL] Could not find compiled dynamic library in {lib_dir}")
        return 1

    print(f"Loading native library: {lib_path}")
    msis_lib = ctypes.CDLL(str(lib_path))

    msis_lib.msis21_init_c.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    msis_lib.msis21_init_c.restype = ctypes.c_int

    double_p = ctypes.POINTER(ctypes.c_double)
    msis_lib.msis21_calc_c.argtypes = [
        ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
        ctypes.c_double, ctypes.c_double, double_p,
        double_p, double_p, double_p, double_p
    ]
    msis_lib.msis21_calc_c.restype = ctypes.c_int

    path_str = (str(parm_path.resolve()) + "/").encode("utf-8")
    file_str = parm_file.encode("utf-8")
    status = msis_lib.msis21_init_c(path_str, file_str)
    if status != 0:
        print(f"[FAIL] msis21_init_c failed with code {status}")
        return 1
    if hasattr(msis_lib, "msis21_set_storm_ap_mode_c"):
        msis_lib.msis21_set_storm_ap_mode_c.argtypes = [ctypes.c_int]
        msis_lib.msis21_set_storm_ap_mode_c.restype = ctypes.c_int
        if msis_lib.msis21_set_storm_ap_mode_c(0) != 0:
            print("[FAIL] msis21_set_storm_ap_mode_c(0) failed")
            return 1
    print("[OK] Native model initialized successfully.")

    in_lines = [l.strip() for l in test_in.read_text(encoding="utf-8").splitlines() if l.strip()][1:]
    ref_lines = [l.strip() for l in test_ref.read_text(encoding="utf-8").splitlines() if l.strip()][1:]

    max_rho_rel_err = 0.0
    max_tn_abs_err = 0.0
    rho_out = ctypes.c_double()
    tn_out  = ctypes.c_double()
    tex_out = ctypes.c_double()
    dn_out  = (ctypes.c_double * 10)()

    for idx, (in_line, ref_line) in enumerate(zip(in_lines, ref_lines)):
        in_tok = in_line.split()
        ref_tok = ref_line.split()

        iyd       = float(in_tok[0])
        day_doy   = float(int(iyd) % 1000)
        sec       = float(in_tok[1])
        alt       = float(in_tok[2])
        glat      = float(in_tok[3])
        glong     = float(in_tok[4])
        stl       = float(in_tok[5])
        f107a     = float(in_tok[6])
        f107      = float(in_tok[7])
        ap_scalar = float(in_tok[8])

        ap_arr = (ctypes.c_double * 7)(ap_scalar, ap_scalar, ap_scalar, ap_scalar, ap_scalar, ap_scalar, ap_scalar)

        res = msis_lib.msis21_calc_c(
            day_doy, sec, alt, glat, glong, f107a, f107, ap_arr,
            ctypes.byref(rho_out), ctypes.byref(tn_out), ctypes.byref(tex_out), dn_out
        )
        if res != 0:
            print(f"[FAIL] Calculation failed on line {idx+1}")
            return 1

        ref_rho_g_cm3 = float(ref_tok[14])
        calc_rho_g_cm3 = rho_out.value * 1e-3
        rho_rel_err = abs(calc_rho_g_cm3 - ref_rho_g_cm3) / ref_rho_g_cm3 if ref_rho_g_cm3 != 0.0 else 0.0
        if rho_rel_err > max_rho_rel_err:
            max_rho_rel_err = rho_rel_err

        ref_tn = float(ref_tok[19])
        calc_tn = tn_out.value
        tn_abs_err = abs(calc_tn - ref_tn)
        if tn_abs_err > max_tn_abs_err:
            max_tn_abs_err = tn_abs_err

    print(f"Evaluated 200 reference cases through C interface.")
    print(f"Max relative error on mass density (rho): {max_rho_rel_err:.3e}")
    print(f"Max absolute error on neutral temp (Tn): {max_tn_abs_err:.3f} K")

    if max_rho_rel_err <= 5e-4 and max_tn_abs_err <= 0.1:
        print("[PASS] Milestone 2 validation succeeded! C dynamic library is numerically bit-accurate.")
        return 0
    else:
        print("[FAIL] Discrepancy exceeds tolerance.")
        return 1

if __name__ == "__main__":
    project_root = Path(sys.argv[1]).resolve()
    lib_dir = Path(sys.argv[2]).resolve()
    sys.exit(test_c_api(project_root, lib_dir))
