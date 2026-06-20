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

python scripts/generate_sbom.py --version $Version
if ($LASTEXITCODE -ne 0) {
    throw "La génération du SBOM a échoué avec le code $LASTEXITCODE"
}

python scripts/extract_changelog.py --version $Version --include-diff --output "dist/EmployeurD-MegaGest-v$Version.release-notes.md"
if ($LASTEXITCODE -ne 0) {
    throw "L'extraction du journal des changements a échoué avec le code $LASTEXITCODE"
}

$PortableExe = "dist/EmployeurD-MegaGest/EmployeurD-MegaGest.exe"
$PortableExeHash = (Get-FileHash -Algorithm SHA256 $PortableExe).Hash
$Signature = Get-AuthenticodeSignature -LiteralPath $PortableExe

$Security = "dist/EmployeurD-MegaGest-v$Version.security.md"
@"
# Rapport sécurité EmployeurD-MegaGest v$Version

- Données de paie: non incluses dans la mise en ligne.
- Packager: cx_Freeze, paquet portable.
- SHA256 exécutable: $PortableExeHash.
- Signature Windows: $($Signature.Status).
- Conversion: locale.
- Mise à jour: vérification explicite, sans envoi de fichiers.
- VirusTotal: rapport joint séparément pour l'exécutable public seulement.
- Mentions légales: voir docs/mentions_legales.md.
"@ | Set-Content -Encoding utf8 $Security

$VirusTotal = "dist/EmployeurD-MegaGest-v$Version.virustotal.md"
@"
# Rapport VirusTotal EmployeurD-MegaGest v$Version

Rapport à produire après l'analyse de l'exécutable public seulement.
Ne jamais soumettre de TXT EmployeurD, SPD, MND, Markdown ou JSON de validation.
"@ | Set-Content -Encoding utf8 $VirusTotal
