"""
User-controlled acquisition and validation helper for upstream NRLMSIS 2.1 source files.

This helper supports the separate-wrapper distribution workflow: ``orekit-nrlmsis21``
does not bundle upstream NRLMSIS 2.1 Fortran source, ``msis21.parm``, or compiled NRLMSIS
binaries. End users independently obtain NRLMSIS 2.1 from the U.S. Naval Research Laboratory
(NRL) under the applicable license agreement (``NRL-SOF-014-1`` or a separate commercial NRL
license), validate the extracted files, and compile the native JNI bridge locally.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, Union

#: Official U.S. Naval Research Laboratory distribution page and tarball URL for NRLMSIS 2.1.
NRL_OFFICIAL_BASE_URL = "https://map.nrl.navy.mil/map/pub/nrl/NRLMSIS/NRLMSIS2.1/"
NRL_OFFICIAL_ARCHIVE_NAME = "nrlmsis2.1.tar.gz"
NRL_OFFICIAL_ARCHIVE_URL = f"{NRL_OFFICIAL_BASE_URL}{NRL_OFFICIAL_ARCHIVE_NAME}"

#: Exact expected byte size of ``msis21.parm`` from the upstream NRLMSIS 2.1 release.
EXPECTED_PARM_BYTES = 536576

#: Expected filenames and Fortran module/subroutine markers required for compilation.
REQUIRED_FORTRAN_FILES: Tuple[Tuple[str, str], ...] = (
    ("msis_constants.F90", r"\bmodule\s+msis_constants\b"),
    ("msis_init.F90", r"\bmodule\s+msis_init\b"),
    ("msis_utils.F90", r"\bmodule\s+msis_utils\b"),
    ("msis_dfn.F90", r"\bmodule\s+msis_dfn\b"),
    ("msis_tfn.F90", r"\bmodule\s+msis_tfn\b"),
    ("msis_gfn.F90", r"\bmodule\s+msis_gfn\b"),
    ("msis_gtd8d.F90", r"\bsubroutine\s+gtd8d\b"),
    ("msis_calc.F90", r"\bmodule\s+msis_calc\b"),
)

UPSTREAM_LICENSE_NAMES: Tuple[str, ...] = (
    "nrlmsis2.1_license.txt",
    "nrlmsis2.1_license..txt",
)


def format_manual_instructions(target_dir: Optional[Union[str, os.PathLike]] = None) -> str:
    """Returns step-by-step instructions for manually downloading, extracting, and building NRLMSIS 2.1."""
    dest = Path(target_dir).as_posix() if target_dir else "/path/to/NRLMSIS2.1"
    return (
        "Manual NRLMSIS 2.1 Acquisition & Local Build Instructions:\n"
        f"  1. Visit the official NRL distribution directory:\n"
        f"       {NRL_OFFICIAL_BASE_URL}\n"
        f"     and review NRL's Open Source Academic Research License Agreement (NRL-SOF-014-1).\n"
        f"     End users are solely responsible for complying with NRL's licensing terms\n"
        f"     (academic/research/non-profit use only unless separate written NRL IP Counsel consent is held).\n"
        f"  2. Download '{NRL_OFFICIAL_ARCHIVE_NAME}' (or the upstream NRLMSIS 2.1 archive) manually.\n"
        f"  3. Extract and validate it into a local directory without altering upstream files:\n"
        f"       python -m orekit_nrlmsis21.acquire --from-archive /path/to/{NRL_OFFICIAL_ARCHIVE_NAME} --target-dir {dest}\n"
        f"  4. Compile the local native JNI shared library against your source directory:\n"
        f"       cmake -S . -B build/local_jni -G Ninja -DCMAKE_BUILD_TYPE=Release -DNRLMSIS21_SOURCE_DIR={dest}\n"
        f"       cmake --build build/local_jni --target nrlmsis21_jni --config Release\n"
        f"  5. Point the Python loader at your local shared library and parameter file:\n"
        f"       NRLMSIS21_LIB_PATH=<build/local_jni/libnrlmsis21_jni.so|.dll>\n"
        f"       NRLMSIS21_PARM_PATH={dest}/msis21.parm"
    )


def validate_nrlmsis21_directory(
    source_dir: Union[str, os.PathLike],
    require_parm: bool = True,
    require_license: bool = True,
) -> Dict[str, Any]:
    """
    Validates that ``source_dir`` contains all expected upstream NRLMSIS 2.1 files.

    Checks the 8 required Fortran ``.F90`` files and their module/subroutine declarations,
    optionally checks ``msis21.parm`` (536,576 bytes), and checks/preserves the upstream
    NRL license file (``nrlmsis2.1_license.txt`` or ``nrlmsis2.1_license..txt``).

    Raises
    ------
    FileNotFoundError
        If the directory or any required file is missing.
    ValueError
        If a required file is empty, malformed, lacks its expected Fortran module,
        or ``msis21.parm`` does not match 536,576 bytes.
    """
    src = Path(source_dir).expanduser().resolve()
    if not src.exists() or not src.is_dir():
        raise FileNotFoundError(
            f"NRLMSIS 2.1 source directory does not exist or is not a directory: '{src}'.\n\n"
            + format_manual_instructions(src)
        )

    missing_fortran = []
    malformed_fortran = []
    fortran_paths: Dict[str, Path] = {}

    for fname, pattern in REQUIRED_FORTRAN_FILES:
        fpath = src / fname
        if not fpath.exists() or not fpath.is_file():
            missing_fortran.append(fname)
            continue
        if fpath.stat().st_size == 0:
            malformed_fortran.append(f"{fname} (empty file)")
            continue
        content = fpath.read_text(encoding="utf-8", errors="ignore")
        if not re.search(pattern, content, flags=re.IGNORECASE):
            malformed_fortran.append(f"{fname} (expected declaration matching '{pattern}' not found)")
            continue
        fortran_paths[fname] = fpath

    if missing_fortran:
        raise FileNotFoundError(
            f"Missing required upstream NRLMSIS 2.1 Fortran file(s) in '{src}': "
            f"{', '.join(missing_fortran)}.\n\n"
            + format_manual_instructions(src)
        )
    if malformed_fortran:
        raise ValueError(
            f"Invalid upstream NRLMSIS 2.1 Fortran source file(s) in '{src}': "
            + "; ".join(malformed_fortran)
        )

    parm_path: Optional[Path] = None
    candidate_parm = src / "msis21.parm"
    if require_parm:
        if not candidate_parm.exists() or not candidate_parm.is_file():
            raise FileNotFoundError(
                f"Required parameter table 'msis21.parm' not found in '{src}'.\n\n"
                + format_manual_instructions(src)
            )
        size = candidate_parm.stat().st_size
        if size != EXPECTED_PARM_BYTES:
            raise ValueError(
                f"Invalid 'msis21.parm' in '{src}': expected {EXPECTED_PARM_BYTES} bytes, found {size} bytes."
            )
        parm_path = candidate_parm
    elif candidate_parm.exists() and candidate_parm.is_file():
        parm_path = candidate_parm

    license_path: Optional[Path] = None
    for lic_name in UPSTREAM_LICENSE_NAMES:
        cand = src / lic_name
        if cand.exists() and cand.is_file() and cand.stat().st_size > 0:
            license_path = cand
            break

    # If upstream tarball uses the double-dot filename typo, preserve a byte-identical canonical copy
    canonical_lic = src / "nrlmsis2.1_license.txt"
    if license_path is not None and license_path.name == "nrlmsis2.1_license..txt" and not canonical_lic.exists():
        shutil.copy2(license_path, canonical_lic)
        license_path = canonical_lic

    if require_license and license_path is None:
        raise FileNotFoundError(
            f"Upstream NRL license file ('nrlmsis2.1_license.txt') not found in '{src}'. "
            "Upstream NRLMSIS 2.1 source directories must retain NRL's original license file."
        )

    return {
        "source_dir": src,
        "fortran_files": fortran_paths,
        "parm_file": parm_path,
        "license_file": license_path,
    }


def _existing_upstream_files(target_dir: Path) -> list[str]:
    names = [f for f, _ in REQUIRED_FORTRAN_FILES] + ["msis21.parm"]
    return [n for n in names if (target_dir / n).exists()]


def _safe_rel_path(member_name: str) -> Optional[Path]:
    clean = member_name.replace("\\", "/").strip("/")
    if not clean:
        return None
    parts = Path(clean).parts
    if any(part in ("..", "") or ":" in part for part in parts):
        raise ValueError(f"Unsafe path traversal entry in archive: '{member_name}'")
    return Path(*parts)


def extract_nrlmsis21_archive(
    archive_path: Union[str, os.PathLike],
    target_dir: Union[str, os.PathLike],
    overwrite: bool = False,
) -> Path:
    """
    Extracts a user-supplied NRLMSIS 2.1 ``.tar.gz``/``.tar``/``.zip`` archive into ``target_dir``
    and validates the 8 required Fortran sources, ``msis21.parm``, and NRL license file.

    Refuses to overwrite pre-existing NRLMSIS files unless ``overwrite=True``.
    """
    arc = Path(archive_path).expanduser().resolve()
    if not arc.exists() or not arc.is_file():
        raise FileNotFoundError(f"Archive file does not exist: '{arc}'.")

    dest = Path(target_dir).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)

    existing = _existing_upstream_files(dest)
    if existing and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing NRLMSIS 2.1 files in '{dest}' "
            f"({', '.join(existing)}). Existing user-supplied NRL source files are always preserved."
        )

    with tempfile.TemporaryDirectory(prefix="nrlmsis21_extract_") as staging_tmp:
        stage = Path(staging_tmp)
        lower_name = arc.name.lower()

        if lower_name.endswith(".zip"):
            with zipfile.ZipFile(arc, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    rel = _safe_rel_path(info.filename)
                    if rel is None:
                        continue
                    out_file = stage / rel
                    out_file.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info, "r") as src_f, open(out_file, "wb") as dst_f:
                        shutil.copyfileobj(src_f, dst_f)
        elif tarfile.is_tarfile(arc):
            with tarfile.open(arc, "r:*") as tf:
                for member in tf.getmembers():
                    if member.isdir():
                        continue
                    if not member.isfile():
                        continue
                    rel = _safe_rel_path(member.name)
                    if rel is None:
                        continue
                    src_f = tf.extractfile(member)
                    if src_f is None:
                        continue
                    out_file = stage / rel
                    out_file.parent.mkdir(parents=True, exist_ok=True)
                    with src_f, open(out_file, "wb") as dst_f:
                        shutil.copyfileobj(src_f, dst_f)
        else:
            raise ValueError(
                f"Unsupported archive format for '{arc.name}'. Expected .tar.gz, .tgz, .tar, or .zip."
            )

        # Locate extracted root folder containing msis_calc.F90 (handles flat or nested archives)
        calc_matches = list(stage.rglob("msis_calc.F90"))
        if not calc_matches:
            raise FileNotFoundError(
                f"Archive '{arc.name}' does not appear to contain 'msis_calc.F90'."
            )
        src_root = calc_matches[0].parent

        validate_nrlmsis21_directory(src_root, require_parm=True, require_license=True)

        for item in src_root.iterdir():
            if item.is_file():
                target_file = dest / item.name
                if target_file.exists() and not overwrite:
                    continue
                shutil.copy2(item, target_file)

    validate_nrlmsis21_directory(dest, require_parm=True, require_license=True)
    return dest


def download_nrlmsis21_source(
    target_dir: Union[str, os.PathLike],
    url: str = NRL_OFFICIAL_ARCHIVE_URL,
    accept_nrl_license: bool = False,
    interactive_input: Callable[[str], str] = input,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> Path:
    """
    Downloads and extracts NRLMSIS 2.1 from the official NRL distribution ONLY after explicit user consent.

    Never downloads silently. When ``accept_nrl_license`` is False, requires interactive ``YES``
    confirmation; otherwise raises ``PermissionError`` before performing any network request.
    """
    dest = Path(target_dir).expanduser().resolve()

    existing = _existing_upstream_files(dest)
    if existing:
        raise FileExistsError(
            f"Refusing to overwrite existing NRLMSIS 2.1 files in '{dest}' "
            f"({', '.join(existing)}). Use --verify to validate your existing directory."
        )

    if not accept_nrl_license:
        banner = (
            "\n========================================================================\n"
            "NRLMSIS 2.1 UPSTREAM SOURCE DOWNLOAD CONFIRMATION\n"
            "========================================================================\n"
            f"Official NRL source URL:\n  {url}\n\n"
            "IMPORTANT LICENSING NOTICE (NRL-SOF-014-1):\n"
            "- Upstream NRLMSIS 2.1 source code and msis21.parm are NOT bundled with\n"
            "  orekit-nrlmsis21 and remain property of the U.S. Government (NRL).\n"
            "- Under NRL-SOF-014-1, NRLMSIS 2.1 is authorized solely for research,\n"
            "  academic, and non-profit use unless written NRL IP Counsel consent is held.\n"
            "- YOU are solely responsible for reviewing and complying with NRL's license.\n"
            "========================================================================\n"
        )
        print(banner)
        is_default_stdin = interactive_input is input
        if is_default_stdin and not sys.stdin.isatty():
            raise PermissionError(
                "Refusing to download upstream NRLMSIS 2.1 non-interactively without explicit "
                "confirmation (pass --accept-nrl-license or accept_nrl_license=True after "
                "reviewing NRL-SOF-014-1).\n\n" + format_manual_instructions(dest)
            )
        answer = interactive_input(
            "Type 'YES' to confirm you accept NRL's license responsibility and wish to download now: "
        ).strip()
        if answer != "YES":
            raise PermissionError(
                "Download cancelled by user (confirmation 'YES' was not given).\n\n"
                + format_manual_instructions(dest)
            )

    with tempfile.TemporaryDirectory(prefix="nrlmsis21_dl_") as dl_tmp:
        archive_path = Path(dl_tmp) / NRL_OFFICIAL_ARCHIVE_NAME
        req = urllib.request.Request(url, headers={"User-Agent": "orekit-nrlmsis21-acquire/1.0.2"})
        with opener(req, timeout=60) as resp, open(archive_path, "wb") as out_f:
            shutil.copyfileobj(resp, out_f)
        extract_nrlmsis21_archive(archive_path, dest, overwrite=False)

    return dest


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m orekit_nrlmsis21.acquire",
        description="User-controlled NRLMSIS 2.1 source verification, extraction, and acquisition helper.",
    )
    parser.add_argument(
        "--target-dir",
        help="Local directory to extract into or validate.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Validate an existing local NRLMSIS 2.1 source directory without modifying or downloading files.",
    )
    parser.add_argument(
        "--from-archive",
        help="Extract and validate a manually downloaded NRLMSIS 2.1 tarball/zip archive.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download NRLMSIS 2.1 from the official NRL URL after explicit user confirmation.",
    )
    parser.add_argument(
        "--accept-nrl-license",
        action="store_true",
        help="Explicitly confirm you accept responsibility for complying with NRL-SOF-014-1 (required for non-interactive --download).",
    )
    parser.add_argument(
        "--url",
        default=NRL_OFFICIAL_ARCHIVE_URL,
        help=f"Override NRL download URL (default: {NRL_OFFICIAL_ARCHIVE_URL}).",
    )
    parser.add_argument(
        "--print-manual-instructions",
        action="store_true",
        help="Print manual download, extraction, and CMake build commands and exit.",
    )

    args = parser.parse_args(argv)

    if args.print_manual_instructions or not any((args.verify, args.from_archive, args.download)):
        print(format_manual_instructions(args.target_dir))
        return 0

    if not args.target_dir:
        parser.error("--target-dir is required with --verify, --from-archive, or --download.")

    try:
        if args.verify:
            info = validate_nrlmsis21_directory(args.target_dir, require_parm=True, require_license=True)
            print(
                f"[OK] Validated NRLMSIS 2.1 directory: {info['source_dir']}\n"
                f"     Fortran files: {len(info['fortran_files'])}/8\n"
                f"     Parameter file: {info['parm_file'].name} ({info['parm_file'].stat().st_size} bytes)\n"
                f"     License file:   {info['license_file'].name}"
            )
            return 0

        if args.from_archive:
            dest = extract_nrlmsis21_archive(args.from_archive, args.target_dir, overwrite=False)
            print(f"[OK] Extracted and validated NRLMSIS 2.1 in: {dest}")
            print(f"     Next: cmake -S . -B build/local_jni -G Ninja -DCMAKE_BUILD_TYPE=Release -DNRLMSIS21_SOURCE_DIR={dest}")
            return 0

        if args.download:
            dest = download_nrlmsis21_source(
                args.target_dir,
                url=args.url,
                accept_nrl_license=args.accept_nrl_license,
            )
            print(f"[OK] Downloaded and validated NRLMSIS 2.1 in: {dest}")
            print(f"     Next: cmake -S . -B build/local_jni -G Ninja -DCMAKE_BUILD_TYPE=Release -DNRLMSIS21_SOURCE_DIR={dest}")
            return 0
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
