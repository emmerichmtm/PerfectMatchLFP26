param(
    [string]$Python = "$PSScriptRoot\.venv\Scripts\python.exe",
    [string]$Destination = "$PSScriptRoot\dist",
    [string]$BuildDirectory = "$PSScriptRoot\build"
)
$ErrorActionPreference = 'Stop'

function Invoke-Python([string]$Failure) {
    # PyInstaller logs to stderr; Windows PowerShell would treat that as an error under 'Stop'.
    # Success or failure is decided by the exit code instead.
    $ErrorActionPreference = 'Continue'
    & $Python @args
    if ($LASTEXITCODE -ne 0) { throw $Failure }
}

Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath $Python)) { throw 'Run setup_windows.bat first, then: .venv\Scripts\python -m pip install pyinstaller==6.22.3' }
    if (-not (Test-Path -LiteralPath 'manual.pdf')) { throw 'manual.pdf is missing: compile manual.tex first (see README).' }
    Invoke-Python 'PyInstaller build failed.' -m PyInstaller --noconfirm --log-level WARN --workpath $BuildDirectory --distpath $Destination PerfectMatchLFP26.spec
    $package = Join-Path $Destination 'PerfectMatchLFP26'
    Invoke-Python 'Adding staff files and notices failed.' package_files.py $package
    $zip = Join-Path $Destination 'PerfectMatchLFP26-Windows.zip'
    # Python zipfile also keeps files that PowerShell Compress-Archive may skip.
    Invoke-Python 'ZIP creation failed.' -m zipfile -c $zip $package
    Write-Host "Ready: $zip"
} finally {
    Pop-Location
}
