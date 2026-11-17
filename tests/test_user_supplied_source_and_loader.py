"""
Targeted tests for the User-Supplied NRLMSIS 2.1 Source Build Architecture and Python Loader Configuration.

Runnable via either `pytest tests/test_user_supplied_source_and_loader.py` or
`python tests/test_user_supplied_source_and_loader.py`.

Tests:
1. Python loader resolution with explicit NRLMSIS21_LIB_PATH and NRLMSIS21_PARM_PATH (files & directories).
2. Python loader validation with missing paths, empty files, and corrupted/wrong-size msis21.parm.
3. CMake configuration with a valid user-supplied NRLMSIS21_SOURCE_DIR (outside the repository).
4. CMake configuration with invalid NRLMSIS21_SOURCE_DIR (non-existent, missing .F90 file, invalid module).
5. Verification that all 8 upstream Fortran files are discovered in the CMake build graph.
6. Verification that the existing development configuration resolves external/NRLMSIS2.1 by default.
7. Verification of setup.py wrapper-only vs bundled-binary packaging configuration.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "python") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "python"))

import orekit_nrlmsis21 as nrl
from orekit_nrlmsis21 import acquire, loader

import io
import tarfile
import zipfile

EXPECTED_FORTRAN_FILES = (
    "msis_constants.F90",
    "msis_init.F90",
    "msis_utils.F90",
    "msis_dfn.F90",
    "msis_tfn.F90",
    "msis_gfn.F90",
    "msis_gtd8d.F90",
    "msis_calc.F90",
)

HAS_DEV_UPSTREAM = (REPO_ROOT / "external" / "NRLMSIS2.1" / "msis_calc.F90").is_file()
HAS_GFORTRAN = shutil.which("gfortran") is not None


def _populate_nrlmsis_dir(dest: Path, *, include_parm: bool = True, include_license: bool = True, lic_name: str = "nrlmsis2.1_license.txt") -> Path:
    """Copies external/NRLMSIS2.1 if present, otherwise creates minimal valid synthetic fixtures for CI."""
    dest.mkdir(parents=True, exist_ok=True)
    dev_dir = REPO_ROOT / "external" / "NRLMSIS2.1"
    if HAS_DEV_UPSTREAM:
        for fname in EXPECTED_FORTRAN_FILES:
            shutil.copy2(dev_dir / fname, dest / fname)
        if include_parm:
            shutil.copy2(dev_dir / "msis21.parm", dest / "msis21.parm")
        if include_license:
            shutil.copy2(dev_dir / "nrlmsis2.1_license.txt", dest / lic_name)
        return dest

    for fname in EXPECTED_FORTRAN_FILES:
        stem = Path(fname).stem
        if fname == "msis_gtd8d.F90":
            body = "subroutine gtd8d()\nend subroutine gtd8d\n"
        else:
            body = f"module {stem}\nend module {stem}\n"
        (dest / fname).write_text(body, encoding="utf-8")
    if include_parm:
        (dest / "msis21.parm").write_bytes(b"\x00" * loader.EXPECTED_PARM_BYTES)
    if include_license:
        pkg_lic = REPO_ROOT / "python" / "orekit_nrlmsis21" / "nrlmsis2.1_license.txt"
        (dest / lic_name).write_bytes(pkg_lic.read_bytes())
    return dest


@contextmanager
def _temp_env(**updates: str | None):
    old = {k: os.environ.get(k) for k in updates}
    try:
        for k, v in updates.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _run_cmake_configure(
    build_dir: Path, extra_args: list[str], env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    cmd = ["cmake", "-S", str(REPO_ROOT), "-B", str(build_dir)] + extra_args
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )


class TestUserSuppliedSourceAndLoader(unittest.TestCase):
    """Targeted verification suite for Phase A, Phase B, and Phase C."""

    def test_01_loader_explicit_env_file_paths(self) -> None:
        """NRLMSIS21_LIB_PATH and NRLMSIS21_PARM_PATH resolve valid user-supplied file paths."""
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            lib_name = loader._get_platform_native_lib_name()
            custom_lib = tmp_path / "custom_bin" / lib_name
            custom_lib.parent.mkdir(parents=True)
            custom_lib.write_bytes(b"\x7fELF_DUMMY_NONEMPTY_BINARY")

            custom_parm = tmp_path / "custom_parm" / "msis21.parm"
            custom_parm.parent.mkdir(parents=True)
            custom_parm.write_bytes(b"\x00" * loader.EXPECTED_PARM_BYTES)

            with _temp_env(NRLMSIS21_LIB_PATH=str(custom_lib), NRLMSIS21_PARM_PATH=str(custom_parm)):
                self.assertEqual(loader.find_native_library(), custom_lib.resolve())
                self.assertEqual(loader.find_parameter_file(), custom_parm.resolve())

    def test_02_loader_explicit_env_directory_paths(self) -> None:
        """NRLMSIS21_LIB_PATH and NRLMSIS21_PARM_PATH also accept parent directories."""
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            lib_name = loader._get_platform_native_lib_name()
            lib_dir = tmp_path / "user_lib_dir"
            lib_dir.mkdir(parents=True)
            custom_lib = lib_dir / lib_name
            custom_lib.write_bytes(b"\x7fELF_DUMMY_NONEMPTY_BINARY")

            parm_dir = tmp_path / "user_parm_dir"
            parm_dir.mkdir(parents=True)
            custom_parm = parm_dir / "msis21.parm"
            custom_parm.write_bytes(b"\x00" * loader.EXPECTED_PARM_BYTES)

            with _temp_env(NRLMSIS21_LIB_PATH=str(lib_dir), NRLMSIS21_PARM_PATH=str(parm_dir)):
                self.assertEqual(loader.find_native_library(), custom_lib.resolve())
                self.assertEqual(loader.find_parameter_file(), custom_parm.resolve())

    def test_03_loader_explicit_function_arguments_override_env(self) -> None:
        """Direct lib_path and parm_path arguments take precedence over environment variables."""
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            lib_name = loader._get_platform_native_lib_name()
            arg_lib = tmp_path / "arg_lib" / lib_name
            arg_lib.parent.mkdir(parents=True)
            arg_lib.write_bytes(b"VALID_BINARY")

            arg_parm = tmp_path / "arg_parm" / "msis21.parm"
            arg_parm.parent.mkdir(parents=True)
            arg_parm.write_bytes(b"\x00" * loader.EXPECTED_PARM_BYTES)

            with _temp_env(
                NRLMSIS21_LIB_PATH=str(tmp_path / "nonexistent.so"),
                NRLMSIS21_PARM_PATH=str(tmp_path / "nonexistent.parm"),
            ):
                self.assertEqual(loader.find_native_library(lib_path=arg_lib), arg_lib.resolve())
                self.assertEqual(loader.find_parameter_file(parm_path=arg_parm), arg_parm.resolve())

    def test_04_loader_missing_and_invalid_paths_raise(self) -> None:
        """Missing paths, empty directories, and wrong-size msis21.parm raise clear errors."""
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            missing_lib = tmp_path / "does_not_exist" / loader._get_platform_native_lib_name()
            with _temp_env(NRLMSIS21_LIB_PATH=str(missing_lib)):
                with self.assertRaisesRegex(FileNotFoundError, "NRLMSIS21_LIB_PATH"):
                    loader.find_native_library()

            empty_dir = tmp_path / "empty_lib_dir"
            empty_dir.mkdir(parents=True)
            with _temp_env(NRLMSIS21_LIB_PATH=str(empty_dir)):
                with self.assertRaisesRegex(FileNotFoundError, "not found inside directory"):
                    loader.find_native_library()

            missing_parm = tmp_path / "missing" / "msis21.parm"
            with _temp_env(NRLMSIS21_PARM_PATH=str(missing_parm)):
                with self.assertRaisesRegex(FileNotFoundError, "NRLMSIS21_PARM_PATH"):
                    loader.find_parameter_file()

            bad_parm = tmp_path / "msis21.parm"
            bad_parm.write_bytes(b"truncated_parm_data")
            with _temp_env(NRLMSIS21_PARM_PATH=str(bad_parm)):
                with self.assertRaisesRegex(ValueError, "expected 536576 bytes"):
                    loader.find_parameter_file()

    @unittest.skipUnless(HAS_DEV_UPSTREAM, "Requires local development checkout with external/NRLMSIS2.1")
    def test_05_loader_default_development_fallback_resolution(self) -> None:
        """Without env overrides, development checkout resolves existing library and msis21.parm."""
        with _temp_env(NRLMSIS21_LIB_PATH=None, NRLMSIS21_PARM_PATH=None, NRLMSIS21_SOURCE_DIR=None):
            lib_resolved = loader.find_native_library()
            parm_resolved = loader.find_parameter_file()
            jars = loader.java_classpaths()

            self.assertTrue(lib_resolved.exists() and lib_resolved.is_file())
            self.assertEqual(parm_resolved.stat().st_size, loader.EXPECTED_PARM_BYTES)
            self.assertEqual(len(jars), 1)
            self.assertTrue(Path(jars[0]).exists())

    @unittest.skipUnless(HAS_GFORTRAN, "Requires gfortran toolchain on PATH for CMake configure")
    def test_06_cmake_valid_user_supplied_source_dir_and_8_files(self) -> None:
        """CMake configures cleanly with a user-supplied NRLMSIS21_SOURCE_DIR and discovers all 8 .F90 files."""
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            user_src = _populate_nrlmsis_dir(tmp_path / "user_nrlmsis21_src", include_parm=False, include_license=False)

            build_dir = tmp_path / "cmake_build_valid"
            res = _run_cmake_configure(build_dir, [f"-DNRLMSIS21_SOURCE_DIR={user_src}"])
            combined = (res.stdout or "") + "\n" + (res.stderr or "")
            self.assertEqual(res.returncode, 0, msg=f"CMake configure failed:\n{combined}")
            self.assertIn(
                f"NRLMSIS 2.1 upstream Fortran source directory: {user_src.as_posix()}",
                combined.replace("\\", "/"),
            )

            generated_text = ""
            for gf in build_dir.rglob("*"):
                if gf.is_file() and gf.suffix in (".ninja", ".make", ".txt", ".cmake"):
                    try:
                        generated_text += gf.read_text(encoding="utf-8", errors="ignore") + "\n"
                    except OSError:
                        pass
            normalized_gen = (
                (combined + "\n" + generated_text)
                .replace("\\", "/")
                .replace("$:", ":")
            )
            self.assertIn("Discovered 8 upstream NRLMSIS 2.1 Fortran files:", normalized_gen)
            for fname in EXPECTED_FORTRAN_FILES:
                expected_ref = f"{user_src.as_posix()}/{fname}"
                self.assertIn(
                    expected_ref,
                    normalized_gen,
                    msg=f"Expected source file {expected_ref} not found in CMake build graph",
                )

    @unittest.skipUnless(HAS_GFORTRAN, "Requires gfortran toolchain on PATH for CMake configure")
    def test_07_cmake_invalid_source_dirs_fail_clearly(self) -> None:
        """CMake fails with clear errors for nonexistent dir, missing .F90 file, or corrupt module."""
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)

            # Case A: Non-existent directory
            bad_dir = tmp_path / "nonexistent_nrlmsis_dir"
            res_a = _run_cmake_configure(
                tmp_path / "build_a", [f"-DNRLMSIS21_SOURCE_DIR={bad_dir}"]
            )
            out_a = (res_a.stdout or "") + "\n" + (res_a.stderr or "")
            self.assertNotEqual(res_a.returncode, 0)
            self.assertIn("NRLMSIS21_SOURCE_DIR does not exist or is not a directory", out_a)

            # Case B: Missing one of the 8 required .F90 files (msis_calc.F90)
            incomplete_src = _populate_nrlmsis_dir(tmp_path / "incomplete_src", include_parm=False, include_license=False)
            (incomplete_src / "msis_calc.F90").unlink()
            res_b = _run_cmake_configure(
                tmp_path / "build_b", [f"-DNRLMSIS21_SOURCE_DIR={incomplete_src}"]
            )
            out_b = (res_b.stdout or "") + "\n" + (res_b.stderr or "")
            self.assertNotEqual(res_b.returncode, 0)
            self.assertIn("Missing required upstream NRLMSIS 2.1 Fortran source file(s)", out_b)
            self.assertIn("msis_calc.F90", out_b)

            # Case C: Corrupted module declaration inside msis_dfn.F90
            corrupt_src = _populate_nrlmsis_dir(tmp_path / "corrupt_src", include_parm=False, include_license=False)
            (corrupt_src / "msis_dfn.F90").write_text("! missing module declaration\n", encoding="utf-8")
            res_c = _run_cmake_configure(
                tmp_path / "build_c", [f"-DNRLMSIS21_SOURCE_DIR={corrupt_src}"]
            )
            out_c = (res_c.stdout or "") + "\n" + (res_c.stderr or "")
            self.assertNotEqual(res_c.returncode, 0)
            self.assertIn("Upstream source validation failed", out_c)
            self.assertIn("msis_dfn.F90", out_c)

    @unittest.skipUnless(HAS_DEV_UPSTREAM and HAS_GFORTRAN, "Requires local development checkout with external/NRLMSIS2.1 and gfortran")
    def test_08_cmake_default_development_source_dir_resolution(self) -> None:
        """Without -DNRLMSIS21_SOURCE_DIR, CMake resolves external/NRLMSIS2.1 by default."""
        with tempfile.TemporaryDirectory() as td:
            build_dir = Path(td) / "cmake_build_default"
            env = os.environ.copy()
            env.pop("NRLMSIS21_SOURCE_DIR", None)

            res = _run_cmake_configure(build_dir, [], env=env)
            combined = (res.stdout or "") + "\n" + (res.stderr or "")
            self.assertEqual(res.returncode, 0, msg=f"Default CMake configure failed:\n{combined}")
            expected_default = (REPO_ROOT / "external" / "NRLMSIS2.1").resolve().as_posix()
            self.assertIn(
                f"NRLMSIS 2.1 upstream Fortran source directory: {expected_default}",
                combined.replace("\\", "/"),
            )

    def test_09_setup_py_wrapper_only_excludes_upstream_binaries_and_parm(self) -> None:
        """Verifies that OREKIT_NRLMSIS21_WRAPPER_ONLY=1 excludes .dll, .so*, and .parm in setup.py."""
        code = (
            "import runpy, setuptools; "
            "captured = {}; "
            "setuptools.setup = lambda **kw: captured.update(kw); "
            "runpy.run_path('setup.py'); "
            "print('PACKAGE_DATA=' + repr(captured['package_data']['orekit_nrlmsis21'])); "
            "print('EXCLUDE_DATA=' + repr(captured['exclude_package_data']['orekit_nrlmsis21']))"
        )
        env = os.environ.copy()
        env["OREKIT_NRLMSIS21_WRAPPER_ONLY"] = "1"
        res = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        out = res.stdout
        pkg_part, excl_part = out.split("EXCLUDE_DATA=")
        self.assertIn("'lib/orekit-nrlmsis21-1.0.2.jar'", pkg_part)
        self.assertNotIn("'lib/*.parm'", pkg_part)
        self.assertIn("'lib/*.dll'", excl_part)
        self.assertIn("'lib/*.so*'", excl_part)
        self.assertIn("'lib/*.parm'", excl_part)
        self.assertIn("'lib/orekit-nrlmsis21-1.0.jar'", excl_part)

    # -----------------------------------------------------------------------
    # 8–10. pymsis-Style Source Acquisition Helper Tests (acquire.py)
    # -----------------------------------------------------------------------

    def _make_synthetic_nrl_tar_bytes(self, include_trailing_dot_lic: bool = False) -> bytes:
        buf = io.BytesIO()
        lic_name = "nrlmsis2.1_license..txt" if include_trailing_dot_lic else "nrlmsis2.1_license.txt"
        with tempfile.TemporaryDirectory() as td:
            src_dir = _populate_nrlmsis_dir(Path(td) / "src", lic_name=lic_name)
            with tarfile.open(fileobj=buf, mode="w:gz") as tf:
                for fname in EXPECTED_FORTRAN_FILES:
                    tf.add(src_dir / fname, arcname=f"NRLMSIS2.1/{fname}")
                tf.add(src_dir / "msis21.parm", arcname="NRLMSIS2.1/msis21.parm")
                tf.add(src_dir / lic_name, arcname=f"NRLMSIS2.1/{lic_name}")
        return buf.getvalue()

    def test_10_acquire_validate_directory_success_and_missing_failures(self) -> None:
        """validate_nrlmsis21_directory passes on complete dir and fails clearly on missing/corrupt files."""
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            valid_dir = _populate_nrlmsis_dir(tmp_path / "valid_nrl")
            info = acquire.validate_nrlmsis21_directory(valid_dir)
            self.assertEqual(len(info["fortran_files"]), 8)
            self.assertEqual(info["parm_file"].stat().st_size, acquire.EXPECTED_PARM_BYTES)
            self.assertTrue(info["license_file"].exists())

            # Missing msis_calc.F90
            d_miss = _populate_nrlmsis_dir(tmp_path / "missing_f90")
            (d_miss / "msis_calc.F90").unlink()
            with self.assertRaisesRegex(FileNotFoundError, "msis_calc.F90"):
                acquire.validate_nrlmsis21_directory(d_miss)

            # Wrong-size msis21.parm
            d_bad_parm = _populate_nrlmsis_dir(tmp_path / "bad_parm")
            (d_bad_parm / "msis21.parm").write_bytes(b"short")
            with self.assertRaisesRegex(ValueError, "536576"):
                acquire.validate_nrlmsis21_directory(d_bad_parm)

    def test_11_acquire_extract_archive_and_preserve_existing(self) -> None:
        """extract_nrlmsis21_archive validates contents, normalizes license, refuses overwrite, and blocks traversal."""
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            arc = tmp_path / "nrlmsis2.1.tar.gz"
            arc.write_bytes(self._make_synthetic_nrl_tar_bytes(include_trailing_dot_lic=True))

            target = tmp_path / "extracted_nrl"
            res_dir = acquire.extract_nrlmsis21_archive(arc, target)
            self.assertEqual(res_dir, target.resolve())
            self.assertTrue((target / "msis_calc.F90").exists())
            self.assertEqual((target / "msis21.parm").stat().st_size, acquire.EXPECTED_PARM_BYTES)
            self.assertTrue((target / "nrlmsis2.1_license.txt").exists())

            # Refuses to overwrite existing NRL files when overwrite=False
            with self.assertRaises(FileExistsError):
                acquire.extract_nrlmsis21_archive(arc, target, overwrite=False)

            # Blocks unsafe path traversal archive entries
            evil_arc = tmp_path / "traversal.tar.gz"
            with tarfile.open(evil_arc, "w:gz") as tf:
                ti = tarfile.TarInfo("../evil.txt")
                data = b"bad"
                ti.size = len(data)
                tf.addfile(ti, io.BytesIO(data))
            with self.assertRaisesRegex(ValueError, "Unsafe path traversal"):
                acquire.extract_nrlmsis21_archive(evil_arc, tmp_path / "evil_dest")

    def test_12_acquire_download_requires_explicit_confirmation(self) -> None:
        """download_nrlmsis21_source makes zero network calls unless user explicitly confirms 'YES'."""
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            called = []

            def fake_opener(req, timeout=60):
                called.append(req.full_url)
                return io.BytesIO(self._make_synthetic_nrl_tar_bytes())

            # 1. Declined interactive confirmation -> PermissionError, 0 network calls
            with self.assertRaises(PermissionError):
                acquire.download_nrlmsis21_source(
                    tmp_path / "declined",
                    interactive_input=lambda _prompt: "no",
                    opener=fake_opener,
                )
            self.assertEqual(called, [])

            # 2. Explicit 'YES' confirmation -> calls official NRL URL and validates extracted source
            dest = acquire.download_nrlmsis21_source(
                tmp_path / "confirmed",
                interactive_input=lambda _prompt: "YES",
                opener=fake_opener,
            )
            self.assertEqual(called, [acquire.NRL_OFFICIAL_ARCHIVE_URL])
            self.assertEqual(len(acquire.validate_nrlmsis21_directory(dest)["fortran_files"]), 8)

    def test_13_local_setup_bridge_discovery_and_user_home_fallback(self) -> None:
        """local_setup locates CMake/native bridge sources and loader discovers ~/.orekit_nrlmsis21."""
        from orekit_nrlmsis21 import local_setup

        bridge_root = local_setup.find_native_bridge_source_root()
        self.assertTrue((bridge_root / "CMakeLists.txt").is_file())
        self.assertTrue((bridge_root / "native" / "nrlmsis21_c_api.F90").is_file())

        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            cache_dir = fake_home / ".orekit_nrlmsis21"
            cache_dir.mkdir(parents=True)
            lib_name = loader._get_platform_native_lib_name()
            fake_lib = cache_dir / lib_name
            fake_lib.write_bytes(b"FAKE_COMPILED_LIB")
            fake_parm = cache_dir / "msis21.parm"
            fake_parm.write_bytes(b"\x00" * loader.EXPECTED_PARM_BYTES)

            old_home = Path.home
            try:
                Path.home = classmethod(lambda cls: fake_home)  # type: ignore[assignment]
                with _temp_env(NRLMSIS21_LIB_PATH=None, NRLMSIS21_PARM_PATH=None, NRLMSIS21_SOURCE_DIR=None):
                    if not HAS_DEV_UPSTREAM:
                        self.assertEqual(loader.find_native_library(), fake_lib.resolve())
                        self.assertEqual(loader.find_parameter_file(), fake_parm.resolve())
            finally:
                Path.home = old_home  # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main(verbosity=2)
