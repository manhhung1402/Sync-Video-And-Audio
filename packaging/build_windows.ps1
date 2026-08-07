$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$specFile = Join-Path $PSScriptRoot "SyncVideo-Audio.spec"

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw "Không tìm thấy ffmpeg trong PATH."
}

Push-Location $PSScriptRoot
try {
    python -m PyInstaller --noconfirm --clean $specFile `
        --distpath (Join-Path $projectRoot "dist") `
        --workpath (Join-Path $projectRoot "build\pyinstaller")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller thất bại với exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

Write-Host "Đã build: $(Join-Path $projectRoot 'dist\SyncVideo-Audio.exe')"
