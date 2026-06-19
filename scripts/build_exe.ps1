param(
    [string]$Name = "EmployeurD-MegaGest",
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"

$Spec = (Resolve-Path -LiteralPath "packaging/windows/EmployeurD-MegaGest.spec").Path

$env:EMG_APP_NAME = $Name
try {
    python -m PyInstaller --clean --noconfirm $Spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller a échoué avec le code $LASTEXITCODE"
    }
} finally {
    Remove-Item Env:\EMG_APP_NAME -ErrorAction SilentlyContinue
}

$Exe = "dist/$Name.exe"
if (Test-Path $Exe) {
    $Hash = Get-FileHash -Algorithm SHA256 $Exe
    $Hash.Hash + "  $Name.exe" | Set-Content -Encoding ascii "dist/$Name-v$Version.exe.sha256"
    Copy-Item -LiteralPath $Exe -Destination "dist/$Name-v$Version.exe" -Force
    Compress-Archive -LiteralPath "dist/$Name-v$Version.exe", "dist/$Name-v$Version.exe.sha256" -DestinationPath "dist/$Name-v$Version.zip" -Force
    $Hash | Format-List
}
