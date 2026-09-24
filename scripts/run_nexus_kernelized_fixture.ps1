[CmdletBinding()]
param(
    [string]$LegacyDb = "C:\Users\Chris\Nexus_Runtime_Source\data\Nexus_Framework_ProdV2.db"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$NDKA_SHA = "693f5011c2d662d9ffe3c966d347cca07c86c2d6"
$PRODUCTION_SHA = "2514a11366f8e7f345bb854c0cfaee8c7b40dddd"
$V5_SHA = "48932a94a58f24f54b2fbe81c9d400ddb32f82ed"

$RigRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$CacheRoot = Join-Path $RigRoot ".kernelized-local"
$RepoCache = Join-Path $CacheRoot "repos"
$RunsRoot = Join-Path $CacheRoot "runs"
New-Item -ItemType Directory -Force -Path $RepoCache, $RunsRoot | Out-Null

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Command,
        [Parameter(Mandatory = $true)][string]$Failure
    )
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $Failure
    }
}

function Ensure-ExactCheckout {
    param(
        [Parameter(Mandatory = $true)][string]$Repository,
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string]$Sha
    )

    if (-not (Test-Path (Join-Path $Destination ".git"))) {
        if (Test-Path $Destination) {
            Remove-Item -Recurse -Force $Destination
        }
        Write-Host "Cloning $Repository ..." -ForegroundColor DarkGray
        Invoke-Checked -Command { gh repo clone $Repository $Destination -- --filter=blob:none } -Failure "Failed to clone $Repository"
    }

    Write-Host "Pinning $Repository to $Sha ..." -ForegroundColor DarkGray
    Invoke-Checked -Command { git -C $Destination fetch origin $Sha --depth=1 } -Failure "Failed to fetch $Repository@$Sha"
    Invoke-Checked -Command { git -C $Destination checkout --detach $Sha } -Failure "Failed to checkout $Repository@$Sha"
    $observed = (git -C $Destination rev-parse HEAD).Trim()
    if ($observed -ne $Sha) {
        throw "$Repository checkout mismatch. Expected $Sha, observed $observed"
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host " NEXUS SYNAPSE - LOCAL KERNELIZED FIXTURE LANE" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "Classification: DEVELOPMENT_FIXTURE / PARTIAL" -ForegroundColor Yellow
Write-Host "NDKA:           $NDKA_SHA"
Write-Host "Production:     $PRODUCTION_SHA"
Write-Host "V5:             $V5_SHA"
Write-Host "Legacy source:  $LegacyDb"
Write-Host ""
Write-Host "This lane uses a fresh disposable V5 database and explicit fixture identity fallback." -ForegroundColor Yellow
Write-Host "It exercises the kernelized runtime locally but is NOT deployed TEST acceptance." -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Path $LegacyDb -PathType Leaf)) {
    throw "Legacy database not found: $LegacyDb"
}

Invoke-Checked -Command { gh auth status } -Failure "GitHub CLI is not authenticated."
Invoke-Checked -Command { git --version } -Failure "Git is not available on PATH."
Invoke-Checked -Command { python --version } -Failure "Python is not available on PATH."

$pythonVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$parts = $pythonVersion.Trim().Split('.')
if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 11)) {
    throw "Kernelized NDKA requires Python 3.11+. Observed $pythonVersion"
}

$NdkaRoot = Join-Path $RepoCache "nexus-synapse-ndka"
$ProductionRoot = Join-Path $RepoCache "nexus-synapse-runtime"
$V5Root = Join-Path $RepoCache "nexus-v5-reconstruction"

Ensure-ExactCheckout -Repository "ChrisCanadian/nexus-synapse-ndka" -Destination $NdkaRoot -Sha $NDKA_SHA
Ensure-ExactCheckout -Repository "ChrisCanadian/nexus-synapse-runtime" -Destination $ProductionRoot -Sha $PRODUCTION_SHA
Ensure-ExactCheckout -Repository "ChrisCanadian/nexus-v5-reconstruction" -Destination $V5Root -Sha $V5_SHA

$VenvRoot = Join-Path $CacheRoot ".venv"
$PythonExe = Join-Path $VenvRoot "Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Host "Creating isolated acceptance venv with system packages available ..." -ForegroundColor DarkGray
    Invoke-Checked -Command { python -m venv --system-site-packages $VenvRoot } -Failure "Failed to create local fixture virtual environment."
}

Invoke-Checked -Command { & $PythonExe -m pip install --disable-pip-version-check --no-deps -e $RigRoot -e $NdkaRoot } -Failure "Failed to install the rig/NDKA into the local fixture environment."

$RunId = Get-Date -Format "yyyyMMdd_HHmmss"
$RunRoot = Join-Path $RunsRoot ("fixture_" + $RunId)
$StateRoot = Join-Path $RunRoot "state"
$EvidenceRoot = Join-Path $RunRoot "evidence"
$ArtifactRoot = Join-Path $RunRoot "artifacts"
New-Item -ItemType Directory -Force -Path $StateRoot, $EvidenceRoot, $ArtifactRoot | Out-Null
$IdentityEnv = Join-Path $StateRoot "identities.env"

Write-Host "Preparing DEVELOPMENT_FIXTURE state ..." -ForegroundColor DarkGray
$PrepOutput = & $PythonExe (Join-Path $RigRoot "scripts\prepare_nexus_kernelized_fixture_state.py") `
    --legacy-source $LegacyDb `
    --target-dir $StateRoot `
    --identity-env $IdentityEnv 2>&1
$PrepExitCode = $LASTEXITCODE
$PrepOutput | ForEach-Object { Write-Host $_ }
if ($PrepExitCode -ne 0) {
    throw "Failed to create fixture state."
}

$PrepJson = ($PrepOutput | Select-Object -Last 1 | Out-String).Trim() | ConvertFrom-Json
$LinkedCount = [int]$PrepJson.linked_identity_count
if ($LinkedCount -eq 0) {
    Write-Host "No DiscordLink rows were found. Linked-user cases will SKIP." -ForegroundColor Yellow
} elseif ($LinkedCount -eq 1) {
    Write-Host "One legacy Discord link found. Cross-user isolation will SKIP." -ForegroundColor Yellow
} else {
    Write-Host "$LinkedCount legacy Discord links found; first two will drive fixture identity lanes." -ForegroundColor DarkGray
}

if (Test-Path $IdentityEnv) {
    Get-Content $IdentityEnv | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) { return }
        $pair = $line.Split('=', 2)
        if ($pair.Count -eq 2) {
            [Environment]::SetEnvironmentVariable($pair[0], $pair[1], 'Process')
        }
    }
}

$env:NEXUS_RIG_PRODUCTION_CHECKOUT = $ProductionRoot
$env:NEXUS_RIG_V5_CHECKOUT = $V5Root
$env:NEXUS_RIG_LEGACY_DB_PATH = (Join-Path $StateRoot "legacy.sqlite")
$env:NEXUS_RIG_ARTIFACT_PATH = $ArtifactRoot
$env:NEXUS_RIG_RUNTIME_PROFILE = "development_fixture"
$env:NEXUS_RIG_PROVIDER_KIND = "fake"
$env:NEXUS_RIG_EXPECT_TOOL_LOOP = "0"
$env:NEXUS_RIG_USER_TZ = "America/Toronto"
$env:NEXUS_DEPLOYMENT_ID = "local-kernelized-fixture-$RunId"
$env:NEXUS_RUNTIME_VERSION = "ndka-fixture-$NDKA_SHA"
$env:NLP_ENABLED = "false"
$env:PYTHONUNBUFFERED = "1"

function ForwardSlash([string]$PathValue) {
    return $PathValue.Replace('\', '/')
}

$ConfigPath = Join-Path $RunRoot "kernelized-fixture.env"
$V5StatePath = ForwardSlash (Join-Path $StateRoot "v5.sqlite")
$EvidencePath = ForwardSlash $EvidenceRoot
$ConfigText = @"
RIG_RUNTIME_ADAPTER=live_runtime_rig_nexus_kernelized.runtime_adapter:create_runtime_adapter
RIG_DATABASE_ADAPTER=live_runtime_rig_nexus_kernelized.database_adapter:create_database_adapter
RIG_CASES=live_runtime_rig_nexus_kernelized.cases:register_cases
RIG_DATABASE_PATH=$V5StatePath
RIG_EVIDENCE_DIR=$EvidencePath
RIG_APPLICATION_LABEL=nexus-kernelized-local-fixture
RIG_PUBLIC_SAFE=true
RIG_INTENTIONAL_FAILURE=false
RIG_NETWORK_REQUIRED=false
RIG_ALLOW_ENV_OVERRIDES=false
"@
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($ConfigPath, $ConfigText, $Utf8NoBom)

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " STARTING LIVE LOCAL FIXTURE CAMPAIGN" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Run directory:  $RunRoot" -ForegroundColor DarkGray
Write-Host "Output mode:    VERBOSE / LIVE" -ForegroundColor DarkGray
Write-Host "Classification: DEVELOPMENT_FIXTURE / PARTIAL" -ForegroundColor Yellow
Write-Host ""

Push-Location $RigRoot
try {
    & $PythonExe -m live_runtime_rig --config $ConfigPath --public-safe --verbose
    $ExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

$ReportScript = Join-Path $RigRoot "scripts\report_nexus_kernelized_incomplete.py"
if (Test-Path $ReportScript) {
    & $PythonExe $ReportScript --evidence-root $EvidenceRoot
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARNING: chain-completion report could not be generated." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
if ($ExitCode -eq 0) {
    Write-Host " LOCAL KERNELIZED FIXTURE CAMPAIGN: PASS" -ForegroundColor Green
} else {
    Write-Host " LOCAL KERNELIZED FIXTURE CAMPAIGN: FAIL ($ExitCode)" -ForegroundColor Red
}
Write-Host " Classification: DEVELOPMENT_FIXTURE / PARTIAL" -ForegroundColor Yellow
Write-Host " Evidence/state: $RunRoot" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

exit $ExitCode
