param(
    [string]$Version = "",
    [ValidateSet("patch", "minor", "major")]
    [string]$Bump = "patch",
    [string[]]$Change = @(),
    [switch]$AllowDirtyStart,
    [switch]$CommitVersion,
    [switch]$Push,
    [switch]$CreateGitHubRelease,
    [switch]$PublishNow,
    [switch]$SubmitVirusTotal,
    [switch]$AllowVirusTotalDetections,
    [string]$VirusTotalApiKey = "",
    [int]$VirusTotalWaitMinutes = 10
)

$ErrorActionPreference = "Stop"

function Assert-LastExitCode([string]$Message) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Message (exit $LASTEXITCODE)"
    }
}

if (-not $AllowDirtyStart) {
    $Status = git status --porcelain
    if ($Status) {
        throw "Le dépôt doit être propre avant une mise en ligne. Utilise -AllowDirtyStart seulement pour préparer localement sans publier."
    }
}

$VersionTemp = New-TemporaryFile
$PrepareArgs = @("scripts/prepare_release.py", "--write", "--version-output", $VersionTemp.FullName)
if ($Version) {
    $PrepareArgs += @("--version", $Version)
} else {
    $PrepareArgs += @("--bump", $Bump)
}
foreach ($Item in $Change) {
    $PrepareArgs += @("--change", $Item)
}

python @PrepareArgs
Assert-LastExitCode "Préparation de la version impossible"
$ReleaseVersion = (Get-Content -LiteralPath $VersionTemp.FullName -Raw).Trim()
Remove-Item -LiteralPath $VersionTemp.FullName -Force

Write-Host "Mise en ligne préparée pour v$ReleaseVersion"

.\scripts\release.ps1 -Version $ReleaseVersion -AllowDirty

$Name = "EmployeurD-MegaGest"
$PortableExe = "dist/$Name/$Name.exe"
$PortableZip = "dist/$Name-v$ReleaseVersion-portable.zip"
$VirusTotalReport = "dist/$Name-v$ReleaseVersion.virustotal.md"

if ($SubmitVirusTotal) {
    $VtArgs = @(
        "scripts/submit_virustotal.py",
        "--file", $PortableExe,
        "--output", $VirusTotalReport,
        "--wait-minutes", "$VirusTotalWaitMinutes",
        "--require-submit"
    )
    if (-not $AllowVirusTotalDetections) {
        $VtArgs += "--fail-on-detections"
    }
    if ($VirusTotalApiKey) {
        $VtArgs += @("--api-key", $VirusTotalApiKey)
    }
    python @VtArgs
    Assert-LastExitCode "Soumission VirusTotal impossible"
} else {
    Write-Host "VirusTotal non soumis. Relance avec -SubmitVirusTotal et VT_API_KEY pour produire le rapport final."
    if ($CreateGitHubRelease) {
        throw "La création d'une mise en ligne GitHub exige -SubmitVirusTotal."
    }
}

if ($CreateGitHubRelease -and $AllowVirusTotalDetections) {
    throw "Une mise en ligne GitHub officielle ne peut pas ignorer les détections VirusTotal."
}

if ($SubmitVirusTotal) {
    $ManifestArgs = @(
        "scripts/generate_release_manifest.py",
        "--version", $ReleaseVersion
    )
    if (-not $AllowVirusTotalDetections) {
        $ManifestArgs += "--require-clean-virustotal"
    }
    python @ManifestArgs
    Assert-LastExitCode "Génération du manifeste de mise en ligne impossible"

    python scripts/append_release_verification.py --version $ReleaseVersion
    Assert-LastExitCode "Ajout du score VirusTotal aux notes de mise en ligne impossible"
}

if ($CommitVersion) {
    git add CHANGELOG.md pyproject.toml src/employeurd_megagest/version.py
    git commit -m "Préparer EmployeurD-MegaGest v$ReleaseVersion"
    Assert-LastExitCode "Commit de version impossible"
} else {
    if ($Push -or $CreateGitHubRelease) {
        throw "Ajoute -CommitVersion avant -Push ou -CreateGitHubRelease pour que le tag pointe sur la bonne version."
    }
    Write-Host "Version et journal des changements préparés localement. Relance avec -CommitVersion pour créer le tag et publier."
    Write-Host "Séquence terminée pour v$ReleaseVersion."
    return
}

$RemainingStatus = git status --porcelain
if ($RemainingStatus) {
    throw "Il reste des changements non commités après le commit de version. Corrige le dépôt avant de créer le tag."
}

$Tag = "v$ReleaseVersion"
git rev-parse -q --verify "refs/tags/$Tag" *> $null
if ($LASTEXITCODE -ne 0) {
    git tag -a $Tag -m "EmployeurD-MegaGest v$ReleaseVersion"
    Assert-LastExitCode "Création du tag impossible"
}

if ($Push) {
    $Branch = (git branch --show-current).Trim()
    git push origin $Branch
    Assert-LastExitCode "Push de la branche impossible"
    git push origin $Tag
    Assert-LastExitCode "Push du tag impossible"
}

if ($CreateGitHubRelease) {
    if (-not $Push) {
        throw "Ajoute -Push pour envoyer la branche et le tag avant de créer la mise en ligne GitHub."
    }
    if (-not (Test-Path $VirusTotalReport)) {
        throw "Rapport VirusTotal manquant: $VirusTotalReport"
    }
    $ReleaseArgs = @(
        "release", "create", $Tag,
        "--title", "EmployeurD-MegaGest v$ReleaseVersion",
        "--notes-file", "dist/$Name-v$ReleaseVersion.release-notes.md",
        $PortableZip,
        "$PortableZip.sha256",
        "dist/$Name-v$ReleaseVersion-portable.exe.sha256",
        "dist/$Name-v$ReleaseVersion.sbom.json",
        "dist/$Name-v$ReleaseVersion.security.md",
        "dist/$Name-v$ReleaseVersion.virustotal.md",
        "dist/$Name-v$ReleaseVersion.release-manifest.json"
    )
    if (-not $PublishNow) {
        $ReleaseArgs = @("release", "create", $Tag, "--draft") + $ReleaseArgs[3..($ReleaseArgs.Length - 1)]
    }
    gh @ReleaseArgs
    Assert-LastExitCode "Création de la mise en ligne GitHub impossible"
}

Write-Host "Séquence terminée pour v$ReleaseVersion."
