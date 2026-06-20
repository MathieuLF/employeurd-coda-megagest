param(
    [string]$Name = "EmployeurD-MegaGest",
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"

$Manifest = (Resolve-Path -LiteralPath "packaging/windows/EmployeurD-MegaGest.manifest").Path
$Icon = (Resolve-Path -LiteralPath "packaging/windows/EmployeurD-MegaGest.ico").Path
$TargetDir = "dist/$Name"
$PortableZip = "dist/$Name-v$Version-portable.zip"

New-Item -ItemType Directory -Path "dist" -Force | Out-Null
Remove-Item -LiteralPath $TargetDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "dist/$Name.exe" -Force -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath "dist" -Filter "$Name-v$Version*" -File -ErrorAction SilentlyContinue | Remove-Item -Force

python -m cx_Freeze `
    --script "src/employeurd_megagest/gui_entry.py" `
    --base gui `
    --target-name $Name `
    --target-dir $TargetDir `
    --manifest $Manifest `
    --icon $Icon `
    --copyright "Copyright 2026 Mathieu Lapointe-Fiset" `
    build_exe
if ($LASTEXITCODE -ne 0) {
    throw "cx_Freeze a échoué avec le code $LASTEXITCODE"
}

Copy-Item -LiteralPath "config" -Destination "$TargetDir/config" -Recurse -Force

$PortableExe = "$TargetDir/$Name.exe"
if (-not (Test-Path $PortableExe)) {
    throw "Exécutable portable introuvable: $PortableExe"
}

$PortableExeHash = Get-FileHash -Algorithm SHA256 $PortableExe
$PortableExeHash.Hash + "  $Name.exe" | Set-Content -Encoding ascii "dist/$Name-v$Version-portable.exe.sha256"

if (Test-Path $PortableZip) {
    Remove-Item -LiteralPath $PortableZip -Force
}
Compress-Archive -LiteralPath $TargetDir -DestinationPath $PortableZip -Force
$PortableZipHash = Get-FileHash -Algorithm SHA256 $PortableZip
$PortableZipHash.Hash + "  $Name-v$Version-portable.zip" | Set-Content -Encoding ascii "$PortableZip.sha256"

$PortableExeHash | Format-List
$PortableZipHash | Format-List
