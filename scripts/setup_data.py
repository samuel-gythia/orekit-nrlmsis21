import sys
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
target_dir = project_root / "orekit-data"
zip_path = project_root / "orekit-data.zip"

# 1. Clean up corrupted or partial previous downloads
if zip_path.exists():
    print(f"Removing corrupted {zip_path.name} ({zip_path.stat().st_size} bytes)...")
    zip_path.unlink()
if target_dir.exists():
    shutil.rmtree(target_dir)

# 2. Try git clone first (fastest and guarantees a clean uncompressed tree)
print("Attempting to clone orekit-data repository via git...")
git_success = False
try:
    res = subprocess.run(
        ["git", "clone", "--depth", "1", "https://gitlab.orekit.org/orekit/orekit-data.git", str(target_dir)],
        capture_output=True, text=True
    )
    if res.returncode == 0:
        print("[OK] Cloned orekit-data repository directly.")
        git_success = True
    else:
        print(f"git clone returned non-zero ({res.returncode}), trying direct download...")
except Exception as exc:
    print(f"git not accessible ({exc}), trying direct download...")

# 3. Fallback: HTTP download with User-Agent header
if not git_success:
    url = "https://gitlab.orekit.org/orekit/orekit-data/-/archive/master/orekit-data-master.zip"
    print(f"Downloading archive from {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp, open(zip_path, "wb") as out:
        shutil.copyfileobj(resp, out)
    print(f"[OK] Downloaded {zip_path.name} ({zip_path.stat().st_size // 1024} KB)")

    print(f"Extracting into {target_dir} ...")
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.infolist():
            parts = Path(member.filename).parts
            if len(parts) > 1:
                dest = target_dir.joinpath(*parts[1:])
                if member.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as src, open(dest, "wb") as dst:
                        dst.write(src.read())

# 4. Verify leap-second and EOP files
tai_utc = list(target_dir.rglob("*UTC-TAI*")) + list(target_dir.rglob("tai-utc.dat"))
if not tai_utc:
    print("[FAIL] Could not find UTC-TAI leap seconds file in orekit-data.")
    sys.exit(1)

print(f"[PASS] Orekit data verified: found {tai_utc[0].name}")
