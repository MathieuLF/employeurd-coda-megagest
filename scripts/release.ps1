param(
    [string]$Version = "0.1.0",
    [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"

$AuditArgs = @("scripts/audit_release_readiness.py", "--version", $Version)
if (-not $AllowDirty) {
    $AuditArgs += "--require-clean"
}
python @AuditArgs
if ($LASTEXITCODE -ne 0) {
    throw "L'audit de préparation a échoué avec le code $LASTEXITCODE"
}

python -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) {
    throw "Les tests ont échoué avec le code $LASTEXITCODE"
}

python -X pycache_prefix=build/pycache -m compileall src
if ($LASTEXITCODE -ne 0) {
    throw "La compilation Python a échoué avec le code $LASTEXITCODE"
}

.\scripts\build_exe.ps1 -Version $Version

$PackageHash = python -c "import sys; sys.path.insert(0, 'src'); from pathlib import Path; from employeurd_megagest.integrity import app_package_sha256; print(app_package_sha256(Path('dist/EmployeurD-MegaGest')) or '')"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($PackageHash)) {
    throw "La génération de l'empreinte du paquet a échoué avec le code $LASTEXITCODE"
}
$PackageHash = $PackageHash.Trim()
$PackageHash + "  EmployeurD-MegaGest-v$Version-package" | Set-Content -Encoding ascii "dist/EmployeurD-MegaGest-v$Version.package.sha256"

python scripts/generate_sbom.py --version $Version
if ($LASTEXITCODE -ne 0) {
    throw "La génération du SBOM a échoué avec le code $LASTEXITCODE"
}

python scripts/extract_changelog.py --version $Version --include-diff --output "dist/EmployeurD-MegaGest-v$Version.release-notes.md"
if ($LASTEXITCODE -ne 0) {
    throw "L'extraction du journal des changements a échoué avec le code $LASTEXITCODE"
}

$PortableExe = "dist/EmployeurD-MegaGest/EmployeurD-MegaGest.exe"

$VirusTotal = "dist/EmployeurD-MegaGest-v$Version.virustotal.md"
@"
# Rapport VirusTotal EmployeurD-MegaGest v$Version

Rapport à produire après l'analyse de l'exécutable public seulement.
Ne jamais soumettre de TXT EmployeurD, rapport de contrôle, MND, Markdown ou JSON de validation.
"@ | Set-Content -Encoding utf8 $VirusTotal
