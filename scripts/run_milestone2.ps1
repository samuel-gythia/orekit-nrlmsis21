$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BuildDir    = Join-Path $ProjectRoot "build\milestone2_c"

Write-Host "=== Milestone 2: Building 64-bit NRLMSIS 2.1 C Dynamic Library ===" -ForegroundColor Cyan

# Optional: point MSYS2_UCRT64_BIN at a 64-bit MSYS2 UCRT64 toolchain (e.g. C:\msys64\ucrt64\bin).
# If unset, gcc/gfortran/cmake/ninja are taken from PATH (they must be 64-bit).
$Ucrt = $env:MSYS2_UCRT64_BIN
$CmakeArgs = @("-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release")
if ($env:NRLMSIS21_SOURCE_DIR) {
    $CmakeArgs += @("-DNRLMSIS21_SOURCE_DIR=$($env:NRLMSIS21_SOURCE_DIR -replace '\\','/')")
}
if ($Ucrt) {
    $env:Path = "$Ucrt;$env:Path"
    $CmakeArgs += @("-DCMAKE_Fortran_COMPILER=$($Ucrt -replace '\\','/')/gfortran.exe",
                    "-DCMAKE_C_COMPILER=$($Ucrt -replace '\\','/')/gcc.exe")
}

# Remove old build artifacts
if (Test-Path $BuildDir) {
    Remove-Item -Recurse -Force $BuildDir
}
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null

Push-Location $BuildDir
try {
    Write-Host "Running CMake configure ..." -ForegroundColor Yellow
    & cmake @CmakeArgs "$ProjectRoot"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "CMake configuration failed."
    }

    Write-Host "Building 64-bit shared library ..." -ForegroundColor Yellow
    & cmake --build . --config Release
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Build failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

Write-Host "[OK] 64-bit library built successfully." -ForegroundColor Green

# Validate C library through 64-bit Python ctypes
Write-Host "Running C-API numerical validation against all 200 reference cases ..." -ForegroundColor Yellow
& python (Join-Path $ProjectRoot "tests\test_c_api.py") "$ProjectRoot" "$BuildDir"
