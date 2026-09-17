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
Write-Host " NEXUS SYNAPSE - LOCAL DOCKER KERNELIZED FIXTURE" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "Classification: DEVELOPMENT_FIXTURE / PARTIAL" -ForegroundColor Yellow
Write-Host "Execution:      LOCAL DOCKER / LIVE TERMINAL STREAM" -ForegroundColor Yellow
Write-Host "NDKA:           $NDKA_SHA"
Write-Host "Production:     $PRODUCTION_SHA"
Write-Host "V5:             $V5_SHA"
Write-Host "Legacy source:  $LegacyDb"
Write-Host ""
Write-Host "This lane mirrors the accepted Linux dependency assembly locally." -ForegroundColor Yellow
Write-Host "It is still NOT deployed TEST acceptance." -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Path $LegacyDb -PathType Leaf)) {
    throw "Legacy database not found: $LegacyDb"
}

Invoke-Checked -Command { gh auth status } -Failure "GitHub CLI is not authenticated."
Invoke-Checked -Command { git --version } -Failure "Git is not available on PATH."
Invoke-Checked -Command { python --version } -Failure "Python is not available on PATH."
Invoke-Checked -Command { docker version } -Failure "Docker is not running or is unavailable. Start Docker Desktop and rerun."

$NdkaRoot = Join-Path $RepoCache "nexus-synapse-ndka"
$ProductionRoot = Join-Path $RepoCache "nexus-synapse-runtime"
$V5Root = Join-Path $RepoCache "nexus-v5-reconstruction"

Ensure-ExactCheckout -Repository "ChrisCanadian/nexus-synapse-ndka" -Destination $NdkaRoot -Sha $NDKA_SHA
Ensure-ExactCheckout -Repository "ChrisCanadian/nexus-synapse-runtime" -Destination $ProductionRoot -Sha $PRODUCTION_SHA
Ensure-ExactCheckout -Repository "ChrisCanadian/nexus-v5-reconstruction" -Destination $V5Root -Sha $V5_SHA

$RunId = Get-Date -Format "yyyyMMdd_HHmmss"
$RunRoot = Join-Path $RunsRoot ("docker_fixture_" + $RunId)
$StateRoot = Join-Path $RunRoot "state"
$EvidenceRoot = Join-Path $RunRoot "evidence"
$ArtifactRoot = Join-Path $RunRoot "artifacts"
New-Item -ItemType Directory -Force -Path $StateRoot, $EvidenceRoot, $ArtifactRoot | Out-Null
$IdentityEnv = Join-Path $StateRoot "identities.env"

Write-Host "Preparing isolated DEVELOPMENT_FIXTURE state ..." -ForegroundColor DarkGray
$PrepOutput = & python (Join-Path $RigRoot "scripts\prepare_nexus_kernelized_fixture_state.py") `
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
    Write-Host "$LinkedCount legacy Discord links found; first two drive fixture identity lanes." -ForegroundColor DarkGray
}

$ConfigPath = Join-Path $RunRoot "kernelized-docker-fixture.env"
$ConfigText = @"
RIG_RUNTIME_ADAPTER=live_runtime_rig_nexus_kernelized.runtime_adapter:create_runtime_adapter
RIG_DATABASE_ADAPTER=live_runtime_rig_nexus_kernelized.database_adapter:create_database_adapter
RIG_CASES=live_runtime_rig_nexus_kernelized.cases:register_cases
RIG_DATABASE_PATH=/run/state/v5.sqlite
RIG_EVIDENCE_DIR=/run/evidence
RIG_APPLICATION_LABEL=nexus-kernelized-local-docker-fixture
RIG_PUBLIC_SAFE=true
RIG_INTENTIONAL_FAILURE=false
RIG_NETWORK_REQUIRED=false
RIG_ALLOW_ENV_OVERRIDES=false
"@
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($ConfigPath, $ConfigText, $Utf8NoBom)

$ShortNdka = $NDKA_SHA.Substring(0, 7)
$ShortV5 = $V5_SHA.Substring(0, 7)
$ImageTag = "nexus-kernelized-fixture-local:$ShortNdka-$ShortV5"
$Dockerfile = Join-Path $RigRoot "containers\Dockerfile.local-kernelized-fixture"

Write-Host ""
Write-Host "Building/reusing Linux dependency-parity image ..." -ForegroundColor Cyan
Write-Host "Image: $ImageTag" -ForegroundColor DarkGray
Invoke-Checked -Command {
    docker build `
        --progress=plain `
        --build-context "v5=$V5Root" `
        --file $Dockerfile `
        --tag $ImageTag `
        $RigRoot
} -Failure "Failed to build the local kernelized fixture image."

$dockerArgs = @(
    "run",
    "--rm",
    "--network", "none",
    "--read-only",
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true",
    "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m",
    "--env-file", $IdentityEnv,
    "-e", "NEXUS_RIG_PRODUCTION_CHECKOUT=/production",
    "-e", "NEXUS_RIG_V5_CHECKOUT=/v5",
    "-e", "NEXUS_RIG_LEGACY_DB_PATH=/run/state/legacy.sqlite",
    "-e", "NEXUS_RIG_ARTIFACT_PATH=/run/artifacts",
    "-e", "NEXUS_RIG_RUNTIME_PROFILE=development_fixture",
    "-e", "NEXUS_RIG_PROVIDER_KIND=fake",
    "-e", "NEXUS_RIG_EXPECT_TOOL_LOOP=0",
    "-e", "NEXUS_RIG_USER_TZ=America/Toronto",
    "-e", "NEXUS_DEPLOYMENT_ID=local-docker-kernelized-fixture-$RunId",
    "-e", "NEXUS_RUNTIME_VERSION=ndka-docker-fixture-$NDKA_SHA",
    "-e", "NLP_ENABLED=false",
    "--mount", "type=bind,source=$RigRoot,target=/rig,readonly",
    "--mount", "type=bind,source=$NdkaRoot,target=/ndka,readonly",
    "--mount", "type=bind,source=$ProductionRoot,target=/production,readonly",
    "--mount", "type=bind,source=$V5Root,target=/v5,readonly",
    "--mount", "type=bind,source=$RunRoot,target=/run",
    $ImageTag,
    "--config", "/run/kernelized-docker-fixture.env",
    "--public-safe",
    "--verbose"
)

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " STARTING LIVE LOCAL DOCKER FIXTURE CAMPAIGN" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Run directory:  $RunRoot" -ForegroundColor DarkGray
Write-Host "Output mode:    VERBOSE / LIVE" -ForegroundColor DarkGray
Write-Host "Network:        NONE" -ForegroundColor DarkGray
Write-Host "Classification: DEVELOPMENT_FIXTURE / PARTIAL" -ForegroundColor Yellow
Write-Host ""

& docker @dockerArgs
$ExitCode = $LASTEXITCODE

$OldPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $RigRoot "src"
    $RunJson = Get-ChildItem $EvidenceRoot -Filter "run.json" -File -Recurse -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -ne $RunJson) {
        & python (Join-Path $RigRoot "scripts\report_nexus_kernelized_incomplete.py") --run-root $RunJson.Directory.FullName
    } else {
        Write-Host "" -ForegroundColor Yellow
        Write-Host "CHAIN COMPLETION REPORT UNAVAILABLE: container exited before run.json was written." -ForegroundColor Yellow
    }
} finally {
    $env:PYTHONPATH = $OldPythonPath
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
if ($ExitCode -eq 0) {
    Write-Host " LOCAL DOCKER KERNELIZED FIXTURE CAMPAIGN: PASS" -ForegroundColor Green
} else {
    Write-Host " LOCAL DOCKER KERNELIZED FIXTURE CAMPAIGN: FAIL ($ExitCode)" -ForegroundColor Red
}
Write-Host " Classification: DEVELOPMENT_FIXTURE / PARTIAL" -ForegroundColor Yellow
Write-Host " Evidence/state: $RunRoot" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

exit $ExitCode
