import urllib.request
import zipfile
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
zip_path = project_root / "orekit-data.zip"
target_dir = project_root / "orekit-data"

url = "https://gitlab.orekit.org/orekit/orekit-data/-/archive/master/orekit-data-master.zip"

if not zip_path.exists():
    print(f"Downloading orekit-data archive from {url} ...")
    urllib.request.urlretrieve(url, zip_path)
    print(f"[OK] Downloaded {zip_path.stat().st_size // 1024} KB")

print(f"Extracting into {target_dir} ...")
target_dir.mkdir(parents=True, exist_ok=True)

with zipfile.ZipFile(zip_path, "r") as z:
    for member in z.infolist():
        parts = Path(member.filename).parts
        # Strip the top-level 'orekit-data-master' folder prefix
        if len(parts) > 1:
            dest = target_dir.joinpath(*parts[1:])
            if member.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(member) as src, open(dest, "wb") as dst:
                    dst.write(src.read())

tai_utc = list(target_dir.rglob("*UTC-TAI*"))
print(f"[OK] Extraction complete. Found {len(tai_utc)} UTC-TAI data file(s):")
for f in tai_utc:
    print(f"  - {f.name}")
