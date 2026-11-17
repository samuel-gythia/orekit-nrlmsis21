import sys
from pathlib import Path
import math

def inspect_fortran_signatures(src_dir: Path) -> None:
    print("=== Upstream Fortran Signature Verification ===")
    targets = ["msis_constants.F90", "msis_init.F90", "msis_calc.F90"]
    for fname in targets:
        fpath = src_dir / fname
        if not fpath.exists():
            print(f"[ERROR] Missing upstream file: {fpath}")
            continue
        print(f"\n--- {fname} ---")
        lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip().lower()
            if any(stripped.startswith(k) for k in [
                "#ifdef", "#else", "#endif", "integer, parameter :: rp",
                "subroutine msisinit", "subroutine msiscalc",
                "real(kind=rp)", "character(len=", "integer, intent", "logical, intent"
            ]):
                print(f"  L{idx:03d}: {line}")

def compare_outputs(out_file: Path, ref_file: Path) -> int:
    print("\n=== Comparing Generated Output vs. NRL Double-Precision Reference ===")
    if not out_file.exists():
        print(f"[FAIL] Generated output file not found: {out_file}")
        return 1
    if not ref_file.exists():
        print(f"[FAIL] Reference file not found: {ref_file}")
        return 1

    out_lines = [l.strip() for l in out_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    ref_lines = [l.strip() for l in ref_file.read_text(encoding="utf-8").splitlines() if l.strip()]

    if len(out_lines) != len(ref_lines):
        print(f"[FAIL] Line count mismatch: generated={len(out_lines)}, reference={len(ref_lines)}")
        return 1

    print(f"Header (Generated): {out_lines[0]}")
    print(f"Header (Reference): {ref_lines[0]}")

    max_abs_err = 0.0
    max_rel_err = 0.0
    worst_info = ""
    num_rows = 0

    for line_idx in range(1, len(ref_lines)):
        out_tokens = out_lines[line_idx].split()
        ref_tokens = ref_lines[line_idx].split()
        if len(out_tokens) != len(ref_tokens):
            print(f"[FAIL] Column count mismatch on data line {line_idx}")
            return 1

        num_rows += 1
        for col_idx, (o_str, r_str) in enumerate(zip(out_tokens, ref_tokens)):
            o_val = float(o_str)
            r_val = float(r_str)
            abs_err = abs(o_val - r_val)
            rel_err = abs_err / abs(r_val) if r_val != 0.0 else abs_err
            if abs_err > max_abs_err:
                max_abs_err = abs_err
            if rel_err > max_rel_err:
                max_rel_err = rel_err
                worst_info = f"row={num_rows}, col={col_idx+1} (gen={o_str}, ref={r_str})"

    print(f"Rows compared     : {num_rows}")
    print(f"Max absolute error: {max_abs_err:.3e}")
    print(f"Max relative error: {max_rel_err:.3e} ({worst_info})")

    # The reference file prints values in 5-significant-digit scientific notation (e.g. 1.2345E+01),
    # so agreement within 1e-4 relative error confirms exact double-precision reproduction.
    if max_rel_err <= 1e-4:
        print("[PASS] Milestone 1 validation succeeded! Output matches NRL double-precision reference.")
        return 0
    else:
        print("[FAIL] Relative error exceeds threshold (1e-4). Check if -DDBLE was passed.")
        return 1

if __name__ == "__main__":
    src_dir = Path(sys.argv[1]).resolve()
    out_dir = Path(sys.argv[2]).resolve()
    inspect_fortran_signatures(src_dir)
    sys.exit(compare_outputs(out_dir / "msis2.1_test_out.txt", src_dir / "msis2.1_test_ref_dp.txt"))
