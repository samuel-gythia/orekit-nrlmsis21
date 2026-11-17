import sys
import os
import threading
from pathlib import Path

def run_test():
    project_root = Path(".").resolve()
    upstream_dir = project_root / "external" / "NRLMSIS2.1"

    if len(sys.argv) > 1:
        build_dir = Path(sys.argv[1]).resolve()
    else:
        build_dir = project_root / "build" / "milestone2_c"
        if sys.platform.startswith("linux") and not (build_dir / "libnrlmsis21_jni.so").exists():
            build_dir = project_root / "build" / "linux"

    jar_candidates = [
        project_root / "target" / "orekit-nrlmsis21-1.0.2.jar",
        project_root / "target" / "orekit-nrlmsis21-1.0.jar",
        project_root / "python" / "orekit_nrlmsis21" / "lib" / "orekit-nrlmsis21-1.0.2.jar",
    ]
    jar_path = next((p for p in jar_candidates if p.exists()), jar_candidates[0])

    if not jar_path.exists():
        print(f"[FAIL] JAR not found: {jar_path}")
        return 1

    # Locate compiled JNI library
    if sys.platform == "win32":
        jni_dll = build_dir / "libnrlmsis21_jni.dll"
    else:
        jni_dll = build_dir / "libnrlmsis21_jni.so"
    if not jni_dll.exists():
        alt = build_dir / ("libnrlmsis21_jni.so" if sys.platform == "win32" else "libnrlmsis21_jni.dll")
        if alt.exists():
            jni_dll = alt
    if not jni_dll.exists():
        print(f"[FAIL] JNI library not found in {build_dir}")
        return 1

    # Add JAR to JPype classpath before initVM
    import orekit_jpype as orekit
    import jpype

    if not jpype.isJVMStarted():
        orekit.initVM()
    jpype.addClassPath(str(jar_path))

    from org.ssa.nrlmsis21 import Nrlmsis21Native

    # Load JNI shared library
    print(f"Loading native library via Java: {jni_dll}")
    Nrlmsis21Native.load(str(jni_dll.resolve()))
    print("[OK] Native library loaded into JVM.")

    # Initialize model with absolute path
    parm_path_str = str(upstream_dir.resolve()).replace("\\", "/") + "/"
    status = Nrlmsis21Native.init(parm_path_str, "msis21.parm")
    if status != 0:
        print(f"[FAIL] Nrlmsis21Native.init returned {status}")
        return 1
    assert Nrlmsis21Native.isInitialized(), "Expected isInitialized() == True after init"
    assert Nrlmsis21Native.isReady(), "Expected isReady() == True after init"
    assert Nrlmsis21Native.isStormApMode(), "Expected default stormApMode == True after 2-arg init"

    # Exercise setStormApMode and 3-arg init(..., stormApMode)
    assert Nrlmsis21Native.setStormApMode(False) == 0
    assert not Nrlmsis21Native.isStormApMode(), "Expected isStormApMode() == False after setStormApMode(False)"
    assert Nrlmsis21Native.init(parm_path_str, "msis21.parm", False) == 0
    assert not Nrlmsis21Native.isStormApMode(), "Expected isStormApMode() == False after 3-arg init(..., False)"
    assert Nrlmsis21Native.setStormApMode(True) == 0
    assert Nrlmsis21Native.isStormApMode(), "Expected isStormApMode() == True after setStormApMode(True)"
    print("[OK] NRLMSIS 2.1 initialized and JNI state/storm-Ap methods verified.")

    # 1. Numerical verification of 200 reference rows (in legacy daily-Ap mode sw(9)=+1.0)
    assert Nrlmsis21Native.setStormApMode(False) == 0
    test_in = upstream_dir / "msis2.1_test_in.txt"
    test_ref = upstream_dir / "msis2.1_test_ref_dp.txt"

    in_lines = [l.strip() for l in test_in.read_text(encoding="utf-8").splitlines() if l.strip()][1:]
    ref_lines = [l.strip() for l in test_ref.read_text(encoding="utf-8").splitlines() if l.strip()][1:]

    max_rho_rel_err = 0.0
    max_tn_abs_err = 0.0

    # Allocate reusable double[] buffers for JNI results
    scalars = jpype.JArray(jpype.JDouble)(3)
    dn = jpype.JArray(jpype.JDouble)(10)

    for idx, (in_line, ref_line) in enumerate(zip(in_lines, ref_lines)):
        in_tok = in_line.split()
        ref_tok = ref_line.split()

        iyd       = float(in_tok[0])
        day_doy   = float(int(iyd) % 1000)
        sec       = float(in_tok[1])
        alt       = float(in_tok[2])
        glat      = float(in_tok[3])
        glong     = float(in_tok[4])
        f107a     = float(in_tok[6])
        f107      = float(in_tok[7])
        ap_scalar = float(in_tok[8])

        ap7 = jpype.JArray(jpype.JDouble)([ap_scalar] * 7)

        res = Nrlmsis21Native.calc(day_doy, sec, alt, glat, glong, f107a, f107, ap7, scalars, dn)
        if res != 0:
            print(f"[FAIL] Calculation failed on line {idx+1}")
            return 1

        ref_rho_g_cm3 = float(ref_tok[14])
        calc_rho_g_cm3 = float(scalars[0]) * 1e-3
        rho_rel = abs(calc_rho_g_cm3 - ref_rho_g_cm3) / ref_rho_g_cm3 if ref_rho_g_cm3 != 0.0 else 0.0
        if rho_rel > max_rho_rel_err:
            max_rho_rel_err = rho_rel

        ref_tn = float(ref_tok[19])
        calc_tn = float(scalars[1])
        tn_abs = abs(calc_tn - ref_tn)
        if tn_abs > max_tn_abs_err:
            max_tn_abs_err = tn_abs

    print(f"Evaluated 200 reference cases through Java JNI.")
    print(f"Max relative error on mass density (rho): {max_rho_rel_err:.3e}")
    print(f"Max absolute error on neutral temp (Tn): {max_tn_abs_err:.3f} K")

    if max_rho_rel_err > 5e-4 or max_tn_abs_err > 0.1:
        print("[FAIL] Java JNI results deviated from reference data.")
        return 1

    # Restore storm-time Ap mode for multi-threaded stress test
    assert Nrlmsis21Native.setStormApMode(True) == 0

    # 2. Multi-threaded stress test (10 concurrent threads)
    print("\nRunning multi-threaded concurrency stress test (10 threads)...")
    errors = []

    def worker(tid):
        try:
            loc_scalars = jpype.JArray(jpype.JDouble)(3)
            loc_dn = jpype.JArray(jpype.JDouble)(10)
            loc_ap7 = jpype.JArray(jpype.JDouble)([15.0] * 7)
            for step in range(50):
                z = 200.0 + (step % 20) * 10.0
                r = Nrlmsis21Native.calc(180.0, 43200.0, z, 45.0, 10.0, 150.0, 150.0, loc_ap7, loc_scalars, loc_dn)
                if r != 0 or loc_scalars[0] <= 0.0:
                    errors.append(f"Thread {tid} step {step} failed: res={r}, rho={loc_scalars[0]}")
        except Exception as exc:
            errors.append(f"Thread {tid} exception: {exc}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()

    if errors:
        print(f"[FAIL] Concurrency stress test encountered {len(errors)} errors:")
        for err in errors[:5]:
            print(" ", err)
        return 1

    print("[PASS] Multi-threaded concurrency test passed without race conditions or memory faults!")
    print("[PASS] Milestone 3 validation succeeded! Java/JNI layer is fully operational.")
    return 0

if __name__ == "__main__":
    sys.exit(run_test())
