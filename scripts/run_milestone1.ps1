$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$UpstreamDir = if ($env:NRLMSIS21_SOURCE_DIR) { $env:NRLMSIS21_SOURCE_DIR } else { Join-Path $ProjectRoot "external\NRLMSIS2.1" }
$BuildDir    = Join-Path $ProjectRoot "build\milestone1_ref"

Write-Host "=== Milestone 1: Unmodified NRLMSIS 2.1 Double-Precision Build ===" -ForegroundColor Cyan

if (-not (Test-Path (Join-Path $UpstreamDir "msis_calc.F90"))) {
    Write-Error "Upstream Fortran files not found in $UpstreamDir. Please place the unmodified NRL NRLMSIS 2.1 sources there first."
}

New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null

# Ordered list of upstream Fortran source files (respecting module dependencies)
$FortranFiles = @(
    "msis_constants.F90",
    "msis_utils.F90",
    "msis_init.F90",
    "msis_gfn.F90",
    "msis_tfn.F90",
    "msis_dfn.F90",
    "msis_calc.F90",
    "msis_gtd8d.F90",
    "msis2.1_test.F90"
) | ForEach-Object { Join-Path $UpstreamDir $_ }

$ExePath = Join-Path $BuildDir "msis2.1_test.exe"

Write-Host "Compiling with gfortran -O3 -cpp -DDBLE ..." -ForegroundColor Yellow
& gfortran -O3 -cpp -DDBLE -J"$BuildDir" -o "$ExePath" $FortranFiles
if ($LASTEXITCODE -ne 0) {
    Write-Error "gfortran compilation failed with exit code $LASTEXITCODE"
}
Write-Host "[OK] Compiled $ExePath" -ForegroundColor Green

# Copy runtime inputs to the build folder (leaving external/NRLMSIS2.1 completely untouched)
Copy-Item (Join-Path $UpstreamDir "msis21.parm")        -Destination $BuildDir -Force
Copy-Item (Join-Path $UpstreamDir "msis2.1_test_in.txt") -Destination $BuildDir -Force

Write-Host "Running msis2.1_test.exe ..." -ForegroundColor Yellow
Push-Location $BuildDir
try {
    & "$ExePath"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "msis2.1_test.exe failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

Write-Host "[OK] Generated $BuildDir\msis2.1_test_out.txt" -ForegroundColor Green

# Run Python numerical comparison and Fortran signature extractor
& python (Join-Path $ProjectRoot "tests\compare_ref_dp.py") "$UpstreamDir" "$BuildDir"
