[CmdletBinding()]
param(
    [string]$LegacyDb = "C:\\Users\\Chris\\SSR_Minimal\\data\\Nexus_Framework_ProdV2.db",
    [string]$V5Db = "C:\\Users\\Chris\\Documents\\Codex\\2026-07-13\\can\\NEXUS_V5_RECONSTRUCTION\\var\\nexus.db",
    [string]$ProviderEnvFile = "C:\\Users\\Chris\\SSR_Minimal\\.env",
    [string]$LegacyChromaDir = "C:\\Users\\Chris\\SSR_Minimal\\data\\chroma_db",
    [ValidateSet("apifree-qwen3.5-397b")]
    [string]$ProviderKind = "apifree-qwen3.5-397b",
    [switch]$PublicSafe
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$SourceScript = Join-Path $PSScriptRoot "run_nexus_attribution_takt_monster.ps1"
$GeneratedScript = Join-Path $PSScriptRoot ".run_nexus_attribution_takt_monster_latest.generated.ps1"

$OldNdka = '0b7ae91064aae6e1351c9789d6722dd60b0f290d'
$NewNdka = 'dcf47598ad441fbeb63dbb4f662adb1b0b1c3e2c'
$OldBusinessBrain = '9e42fe0c6d6254745dc52c73b7d6755c0342932e'
$NewBusinessBrain = 'd1aa0a6e25da0a97f0fe6fef54c4406c0328076d'

$text = [System.IO.File]::ReadAllText($SourceScript)
if (-not $text.Contains($OldNdka)) {
    throw "Base Monster launcher no longer contains expected NDKA pin $OldNdka"
}
if (-not $text.Contains($OldBusinessBrain)) {
    throw "Base Monster launcher no longer contains expected Business Brain pin $OldBusinessBrain"
}
$text = $text.Replace($OldNdka, $NewNdka).Replace($OldBusinessBrain, $NewBusinessBrain)

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($GeneratedScript, $text, $Utf8NoBom)

$params = @{
    LegacyDb = $LegacyDb
    V5Db = $V5Db
    ProviderEnvFile = $ProviderEnvFile
    LegacyChromaDir = $LegacyChromaDir
    ProviderKind = $ProviderKind
}
if ($PublicSafe) {
    $params.PublicSafe = $true
}

try {
    & $GeneratedScript @params
    $code = $LASTEXITCODE
} finally {
    Remove-Item -Force $GeneratedScript -ErrorAction SilentlyContinue
}
exit $code
