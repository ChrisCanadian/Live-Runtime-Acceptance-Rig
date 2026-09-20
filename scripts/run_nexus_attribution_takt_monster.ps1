[CmdletBinding()]
param(
    [string]$LegacyDb = "C:\Users\Chris\SSR_Minimal\data\Nexus_Framework_ProdV2.db",
    [string]$V5Db = "C:\Users\Chris\Documents\Codex\2026-07-13\can\NEXUS_V5_RECONSTRUCTION\var\nexus.db",
    [string]$ProviderEnvFile = "C:\Users\Chris\SSR_Minimal\.env",
    [string]$LegacyChromaDir = "C:\Users\Chris\SSR_Minimal\data\chroma_db",
    [ValidateSet("apifree-qwen3.5-397b")]
    [string]$ProviderKind = "apifree-qwen3.5-397b",
    [switch]$PublicSafe
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$NDKA_SHA = "1c097aae4bd9c33ab84b93d6ec941d093d387d4e"
$PRODUCTION_SHA = "2514a11366f8e7f345bb854c0cfaee8c7b40dddd"
$V5_SHA = "c2751a7dff79b6b4d770624706b6ce3d9e51d67f"
$BUSINESS_BRAIN_SHA = "81cc09f064e741a828a5e29fba0bcfee1487e4ea"
$MOON_SOURCE_SHA = "f0cee0018e8cd8d0bfe2434956c8878e4c3cb44b"
$HZK_SHA = "c93b481f2ccfcc5ab4bd74f0abd09a9375b577f6"

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
    if ($LASTEXITCODE -ne 0) { throw $Failure }
}


function Read-DotEnv {
    param([Parameter(Mandatory = $true)][string]$Path)
    $values = @{}
    if (-not (Test-Path $Path -PathType Leaf)) { return $values }
    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $index = $trimmed.IndexOf("=")
        if ($index -le 0) { continue }
        $name = $trimmed.Substring(0, $index).Trim()
        $value = $trimmed.Substring($index + 1).Trim()
        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $values[$name] = $value
    }
    return $values
}

function Require-RealProviderConfiguration {
    param(
        [Parameter(Mandatory = $true)][hashtable]$DotEnv,
        [Parameter(Mandatory = $true)][string]$Kind
    )
    if ($Kind -eq "apifree-qwen3.5-397b") {
        $key = [Environment]::GetEnvironmentVariable("NEXUS_APIFREE_API_KEY")
        if (-not $key) { $key = [Environment]::GetEnvironmentVariable("APIFREE_API_KEY") }
        if (-not $key -and $DotEnv.ContainsKey("NEXUS_APIFREE_API_KEY")) {
            $key = $DotEnv["NEXUS_APIFREE_API_KEY"]
        }
        if (-not $key -and $DotEnv.ContainsKey("APIFREE_API_KEY")) {
            $key = $DotEnv["APIFREE_API_KEY"]
        }
        if (-not $key) {
            throw "Real Monster provider requested but APIFree credential is unavailable. No fake fallback is allowed."
        }
        $env:NEXUS_APIFREE_API_KEY = $key
        $env:NEXUS_APIFREE_AVAILABILITY_REASON = ""
        return
    }
    throw "Unsupported real Monster provider kind: $Kind"
}

function Write-LocalProductionNlpRequirement {
    # Policy declaration only. The Windows host is NOT proof that the Linux
    # Monster image can execute production NLP. The Dockerfile contains the
    # package/model closure smoke, and only a successful image build earns the
    # VERIFIED statement below.
    Write-Host "NLP analyzer policy: full local production pipeline required; Linux image proof pending" -ForegroundColor DarkGray
}

function Ensure-ExactCheckout {
    param(
        [Parameter(Mandatory = $true)][string]$Repository,
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string]$Sha
    )
    if (-not (Test-Path (Join-Path $Destination ".git"))) {
        if (Test-Path $Destination) { Remove-Item -Recurse -Force $Destination }
        Invoke-Checked -Command { gh repo clone $Repository $Destination -- --filter=blob:none --quiet } -Failure "Failed to clone $Repository"
    }
    Invoke-Checked -Command { git -C $Destination fetch --quiet origin $Sha --depth=1 } -Failure "Failed to fetch $Repository@$Sha"
    Invoke-Checked -Command { git -C $Destination checkout --quiet --detach $Sha } -Failure "Failed to checkout $Repository@$Sha"
    # Cached Windows clones may still contain worktree bytes produced under an
    # older .gitattributes policy. Hard-reset after the target commit is active
    # so byte-exact staged donor files are rewritten using the target attributes.
    Invoke-Checked -Command { git -C $Destination reset --quiet --hard $Sha } -Failure "Failed to normalize checkout $Repository@$Sha"
    $observed = (git -C $Destination rev-parse HEAD).Trim()
    if ($observed -ne $Sha) { throw "$Repository checkout mismatch. Expected $Sha, observed $observed" }
}

$EvidenceMode = if ($PublicSafe) { "PUBLIC-SAFE / REDACTED" } else { "LOCAL DEBUG / FULL EVIDENCE" }
$PublicSafeValue = if ($PublicSafe) { "true" } else { "false" }

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Magenta
Write-Host " NEXUS SYNAPSE - ATTRIBUTION + TAKT FULL MONSTER RIG" -ForegroundColor Magenta
Write-Host "======================================================================" -ForegroundColor Magenta
Write-Host "Classification: ISOLATED USER18 / ATTRIBUTION COMPOSITION / TAKT OBSERVATION" -ForegroundColor Yellow
Write-Host "Ingress:        CANONICAL /v1/chat/completions" -ForegroundColor Yellow
Write-Host "Execution:      LOCAL DOCKER / LIVE TERMINAL STREAM / REAL LLM" -ForegroundColor Yellow
Write-Host "Evidence mode:  $EvidenceMode" -ForegroundColor Yellow
Write-Host "NDKA:           $NDKA_SHA"
Write-Host "Production:     $PRODUCTION_SHA"
Write-Host "V5 donor ref:   $V5_SHA"
Write-Host "Business Brain: $BUSINESS_BRAIN_SHA"
Write-Host "Moon Source:    $MOON_SOURCE_SHA"
Write-Host "Provider:       $ProviderKind (REAL external inference)" -ForegroundColor Yellow
Write-Host ""
Write-Host "GREEN means all required flight controls actually executed and passed." -ForegroundColor Yellow
Write-Host "Required controls never disappear behind SKIP." -ForegroundColor Yellow
Write-Host "This is local isolated-state evidence with REAL model inference, NOT deployed TEST acceptance." -ForegroundColor Yellow
Write-Host "Fake provider fallback is forbidden in this lane." -ForegroundColor Yellow
Write-Host "Timing policy: observer wall-clock + existing KernelReceipt.duration_ms only." -ForegroundColor Yellow
Write-Host "External systems are timed only at our call boundary; no contract-invasive instrumentation." -ForegroundColor Yellow
if (-not $PublicSafe) {
    Write-Host "Developer debug is enabled: local evidence may contain exception details and paths." -ForegroundColor Yellow
}
Write-Host ""

if (-not (Test-Path $LegacyDb -PathType Leaf)) { throw "Legacy database not found: $LegacyDb" }
if (-not (Test-Path $V5Db -PathType Leaf)) { throw "V5 state database not found: $V5Db" }
if (-not (Test-Path $LegacyChromaDir -PathType Container)) {
    throw "Production ChromaDB directory not found: $LegacyChromaDir"
}

try {
    $OllamaTags = Invoke-RestMethod -Method Get -Uri "http://localhost:11434/api/tags" -TimeoutSec 5
} catch {
    throw "Local Ollama is required for production RAG embeddings but is not reachable at http://localhost:11434."
}
$OllamaModels = @($OllamaTags.models | ForEach-Object { [string]$_.name })
if (-not ($OllamaModels | Where-Object { $_ -like "nomic-embed-text*" })) {
    throw "Production RAG requires nomic-embed-text, but that model is not installed in local Ollama."
}
Write-Host "RAG embedding host: VERIFIED (nomic-embed-text)" -ForegroundColor DarkGray

$ProviderEnv = Read-DotEnv -Path $ProviderEnvFile
Require-RealProviderConfiguration -DotEnv $ProviderEnv -Kind $ProviderKind
Write-LocalProductionNlpRequirement

& gh auth status *> $null
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI is not authenticated." }
Write-Host "GitHub auth: VERIFIED" -ForegroundColor DarkGray
& git --version *> $null
if ($LASTEXITCODE -ne 0) { throw "Git is not available on PATH." }
& python --version *> $null
if ($LASTEXITCODE -ne 0) { throw "Python is not available on PATH." }
& docker version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker is not running or is unavailable. Start Docker Desktop and rerun."
}
$DockerServerVersion = (& docker version --format '{{.Server.Version}}').Trim()
Write-Host "Host tools: VERIFIED (Git / Python / Docker Engine $DockerServerVersion)" -ForegroundColor DarkGray

$NdkaRoot = Join-Path $RepoCache "nexus-synapse-ndka"
$ProductionRoot = Join-Path $RepoCache "nexus-synapse-runtime"
$V5Root = Join-Path $RepoCache "nexus-v5-reconstruction"
$BusinessBrainRoot = Join-Path $RepoCache "business-brain-attribution"
$MoonSourceRoot = Join-Path $RepoCache "Moon-Source"
$HzkRoot = Join-Path $RepoCache "memex-zettelkasten-hypercube"
Ensure-ExactCheckout -Repository "ChrisCanadian/nexus-synapse-ndka" -Destination $NdkaRoot -Sha $NDKA_SHA
Ensure-ExactCheckout -Repository "ChrisCanadian/nexus-synapse-runtime" -Destination $ProductionRoot -Sha $PRODUCTION_SHA
Ensure-ExactCheckout -Repository "ChrisCanadian/nexus-v5-reconstruction" -Destination $V5Root -Sha $V5_SHA
Ensure-ExactCheckout -Repository "ChrisCanadian/business-brain" -Destination $BusinessBrainRoot -Sha $BUSINESS_BRAIN_SHA
Ensure-ExactCheckout -Repository "luahelenammc/Moon-Source" -Destination $MoonSourceRoot -Sha $MOON_SOURCE_SHA
Ensure-ExactCheckout -Repository "beckmanjon/memex-zettelkasten-hypercube" -Destination $HzkRoot -Sha $HZK_SHA
Write-Host "Attribution sources + HZK treaty: VERIFIED and pinned" -ForegroundColor DarkGray

$SnapshotAttribute = (git -C $NdkaRoot check-attr text -- "migration_staging/v5_snapshot/migrations/0001_core.sql").Trim()
if ($SnapshotAttribute -notmatch "text: unset$") {
    throw "NDKA staged V5 byte-preservation attribute is not active: $SnapshotAttribute"
}
Write-Host "Staged V5 byte policy: VERIFIED (-text)" -ForegroundColor DarkGray

# Windows Git checkouts can retain CRLF worktree bytes even after the attribute
# policy is corrected. Re-materialize the entire staged donor closure directly
# from Git blob objects, then let the NDKA runtime verifier independently verify
# the same bytes again inside Docker.
$Materializer = Join-Path $RigRoot "scripts\materialize_ndka_staged_v5_exact.py"
$MaterializeOutput = & python $Materializer --repo $NdkaRoot --commit $NDKA_SHA 2>&1
$MaterializeExitCode = $LASTEXITCODE
if ($MaterializeExitCode -ne 0) {
    $MaterializeOutput | ForEach-Object { Write-Host $_ }
    throw "Failed to materialize byte-exact staged V5 snapshot."
}
$StagedSample = Join-Path $NdkaRoot "migration_staging\v5_snapshot\migrations\0001_core.sql"
$StagedSampleBytes = (Get-Item $StagedSample).Length
if ($StagedSampleBytes -ne 2203) {
    throw "Staged V5 byte materialization failed host preflight. Expected 2203 bytes, observed $StagedSampleBytes."
}
Write-Host "Staged V5 host bytes: VERIFIED (0001_core.sql = 2203 bytes)" -ForegroundColor DarkGray

$RunId = Get-Date -Format "yyyyMMdd_HHmmss"
$RunRoot = Join-Path $RunsRoot ("attribution_takt_monster_" + $RunId)
$StateRoot = Join-Path $RunRoot "state"
$EvidenceRoot = Join-Path $RunRoot "evidence"
$ArtifactRoot = Join-Path $RunRoot "artifacts"
New-Item -ItemType Directory -Force -Path $StateRoot, $EvidenceRoot, $ArtifactRoot | Out-Null

# Copy BOTH live state sources into disposable Monster state. Source DBs are
# read-only inputs and are never mutated by the campaign.
$IdentityEnv = Join-Path $StateRoot "identities.env"
Write-Host "Preparing isolated User 18 acceptance state ..." -ForegroundColor DarkGray
$PrepOutput = & python (Join-Path $NdkaRoot "scripts\prepare_kernelized_acceptance_state.py") `
    --v5-source $V5Db `
    --legacy-source $LegacyDb `
    --production-checkout $ProductionRoot `
    --target-dir $StateRoot `
    --identity-env $IdentityEnv 2>&1
$PrepExitCode = $LASTEXITCODE
if ($PrepExitCode -ne 0) {
    $PrepOutput | ForEach-Object { Write-Host $_ }
    throw "Failed to create Monster state copies."
}
Write-Host "Isolated Monster state: PREPARED" -ForegroundColor DarkGray

# Build a disposable, self-contained production checkout for the Monster.
# Production memory code resolves its Chroma path relative to the production
# checkout itself. Mounting /production read-only and then trying to overlay
# /production/data is not portable on Docker Desktop: runc must create the
# nested mountpoint inside the read-only parent and fails before the container
# starts. A disposable clone keeps the pinned donor source immutable while
# giving only the Monster-owned copy a writable data directory.
$ProductionRuntimeRoot = Join-Path $StateRoot "production-runtime"
Write-Host "Preparing disposable production donor ..." -ForegroundColor DarkGray
Invoke-Checked -Command {
    git clone --quiet --no-hardlinks $ProductionRoot $ProductionRuntimeRoot
} -Failure "Failed to create disposable production runtime checkout."
Invoke-Checked -Command {
    git -C $ProductionRuntimeRoot checkout --quiet --detach $PRODUCTION_SHA
} -Failure "Failed to pin disposable production runtime checkout."
$RuntimeProductionSha = (git -C $ProductionRuntimeRoot rev-parse HEAD).Trim()
if ($RuntimeProductionSha -ne $PRODUCTION_SHA) {
    throw "Disposable production runtime checkout mismatch. Expected $PRODUCTION_SHA, observed $RuntimeProductionSha"
}

$ProductionDataRoot = Join-Path $ProductionRuntimeRoot "data"
$StateChroma = Join-Path $ProductionDataRoot "chroma_db"
New-Item -ItemType Directory -Force -Path $ProductionDataRoot | Out-Null
Write-Host "Preparing isolated RAG state ..." -ForegroundColor DarkGray
Copy-Item -Path $LegacyChromaDir -Destination $StateChroma -Recurse -Force
if (-not (Test-Path $StateChroma -PathType Container)) {
    throw "Disposable ChromaDB copy was not created."
}
Write-Host "Production donor + RAG state: VERIFIED" -ForegroundColor DarkGray

$ConfigPath = Join-Path $RunRoot "nexus-monster.env"
$ConfigText = @"
RIG_RUNTIME_ADAPTER=live_runtime_rig_nexus_monster.runtime_adapter_contract:create_runtime_adapter
RIG_DATABASE_ADAPTER=live_runtime_rig_nexus_kernelized.database_adapter:create_database_adapter
RIG_CASES=live_runtime_rig_nexus_monster.cases:register_cases
RIG_DATABASE_PATH=/run/state/v5.sqlite
RIG_EVIDENCE_DIR=/run/evidence
RIG_APPLICATION_LABEL=nexus-attribution-takt-full-monster
RIG_PUBLIC_SAFE=$PublicSafeValue
RIG_INTENTIONAL_FAILURE=false
RIG_NETWORK_REQUIRED=true
RIG_ALLOW_ENV_OVERRIDES=false
"@
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($ConfigPath, $ConfigText, $Utf8NoBom)

$ShortNdka = $NDKA_SHA.Substring(0, 7)
$ShortV5 = $V5_SHA.Substring(0, 7)
$ImageTag = "nexus-kernelized-fixture-local:$ShortNdka-$ShortV5"
$Dockerfile = Join-Path $RigRoot "containers\Dockerfile.ndka-full-monster-real"

Write-Host ""
Write-Host "Building/reusing Linux runtime image ..." -ForegroundColor Cyan
$BuildOutput = & docker build `
    --quiet `
    --build-context "v5=$V5Root" `
    --file $Dockerfile `
    --tag $ImageTag `
    $RigRoot 2>&1
$BuildExitCode = $LASTEXITCODE
if ($BuildExitCode -ne 0) {
    $BuildOutput | ForEach-Object { Write-Host $_ }
    throw "Failed to build the local monster runtime image."
}
Write-Host "Linux runtime image: VERIFIED (dependency + offline NLP/model closure)" -ForegroundColor DarkGray

$dockerArgs = @(
    "run",
    "--rm",
    "--network", "bridge",
    "--read-only",
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true",
    "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m",
    "-e", "NEXUS_RIG_PRODUCTION_CHECKOUT=/production",
    "-e", "NEXUS_RIG_V5_CHECKOUT=/v5",
    "-e", "NEXUS_RIG_LEGACY_DB_PATH=/run/state/legacy.sqlite",
    "-e", "NEXUS_RIG_ARTIFACT_PATH=/run/artifacts",
    "-e", "NEXUS_RIG_RUNTIME_PROFILE=development_fixture",
    "-e", "NEXUS_RIG_PROVIDER_KIND=$ProviderKind",
    "-e", "NEXUS_RIG_ATTRIBUTION_CHAIN=1",
    "-e", "NEXUS_RIG_TAKT=1",
    "-e", "NEXUS_RIG_BUSINESS_BRAIN_CHECKOUT=/business-brain",
    "-e", "NEXUS_RIG_MOON_SOURCE_DIR=/moon-source",
    "-e", "NEXUS_RIG_BUSINESS_BRAIN_DB_PATH=/run/state/business-brain-attribution.db",
    "-e", "NEXUS_RIG_HZK_CHECKOUT=/hzk",
    "-e", "NEXUS_RIG_HZK_TREATY_REQUIRED=1",
    "-e", "NEXUS_RIG_ATTRIBUTION_DEADLINE_SECONDS=900",
    "-e", "NEXUS_RIG_PROVIDER_DEADLINE_SECONDS=420",
    "-e", "PYTHONPATH=/rig/src:/ndka/src:/v5/src:/business-brain:/business-brain/src:/hzk/runtime",
    "-e", "NEXUS_APIFREE_API_KEY",
    "-e", "NEXUS_APIFREE_AVAILABILITY_REASON=",
    "-e", "NEXUS_RIG_PRIMARY_USER_ID=18",
    "-e", "NEXUS_RIG_SECONDARY_USER_ID=19",
    "-e", "NEXUS_RIG_PRIMARY_OWNER_KEY=nexus",
    "-e", "NEXUS_RIG_SECONDARY_OWNER_KEY=nexus-secondary-acceptance",
    "-e", "NEXUS_RIG_MONSTER_PERMISSIONS=memory:read,tools:document,artifacts:create,artifacts:read,jobs:create,jobs:read",
    "-e", "NEXUS_DEPLOYMENT_ID=local-monster-$RunId",
    "-e", "NEXUS_RUNTIME_VERSION=ndka-monster-$NDKA_SHA",
    "-e", "NLP_ENABLED=true",
    "-e", "NLP_ZERO_SHOT_API=local",
    "-e", "NLP_EMOTION_API=local",
    "-e", "NLP_USE_CPU_ONLY=true",
    "-e", "NLP_BART_USE_GPU=false",
    "-e", "NLP_OTHER_USE_CPU=true",
    "-e", "HF_HUB_OFFLINE=1",
    "-e", "TRANSFORMERS_OFFLINE=1",
    "-e", "HF_HUB_DISABLE_PROGRESS_BARS=1",
    "-e", "TRANSFORMERS_VERBOSITY=error",
    "-e", "TOKENIZERS_PARALLELISM=false",
    "-e", "TQDM_DISABLE=1",
    "-e", "OLLAMA_EMBEDDING_URL=http://host.docker.internal:11434",
    "--mount", "type=bind,source=$RigRoot,target=/rig,readonly",
    "--mount", "type=bind,source=$NdkaRoot,target=/ndka,readonly",
    "--mount", "type=bind,source=$V5Root,target=/v5,readonly",
    "--mount", "type=bind,source=$BusinessBrainRoot,target=/business-brain,readonly",
    "--mount", "type=bind,source=$MoonSourceRoot,target=/moon-source,readonly",
    "--mount", "type=bind,source=$HzkRoot,target=/hzk,readonly",
    "--mount", "type=bind,source=$ProductionRuntimeRoot,target=/production",
    "--mount", "type=bind,source=$RunRoot,target=/run",
    $ImageTag,
    "--config", "/run/nexus-monster.env"
)
if ($PublicSafe) {
    $dockerArgs += "--public-safe"
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host " STARTING ATTRIBUTION + TAKT FULL MONSTER CAMPAIGN" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "Run directory: $RunRoot" -ForegroundColor DarkGray
Write-Host "Output mode:   COCKPIT / LIVE (full detail retained in evidence)" -ForegroundColor DarkGray
Write-Host "Evidence mode: $EvidenceMode" -ForegroundColor DarkGray
Write-Host "Network:       BRIDGE (required for real provider)" -ForegroundColor DarkGray
Write-Host "Provider:      $ProviderKind / REAL" -ForegroundColor DarkGray
Write-Host "Ingress:       /v1/chat/completions" -ForegroundColor DarkGray
Write-Host "Attribution:   Moon Source -> HZK Treaty v0.3 -> Business Brain -> canonical Nexus" -ForegroundColor DarkGray
Write-Host "Deadline:      provider 420s hard / stage 10A 900s hard" -ForegroundColor DarkGray
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
        $Reporter = Join-Path $RigRoot "scripts\report_nexus_monster_incomplete.py"
        if ($PublicSafe) {
            & python $Reporter --run-root $RunJson.Directory.FullName --public-safe
        } else {
            & python $Reporter --run-root $RunJson.Directory.FullName
        }
    } else {
        Write-Host ""
        Write-Host "MONSTER CHAIN COMPLETION REPORT UNAVAILABLE: container exited before run.json was written." -ForegroundColor Yellow
    }
} finally {
    $env:PYTHONPATH = $OldPythonPath
}

# Re-verify that the pinned cached donor checkout was not modified while the
# writable disposable runtime clone was in use.
$CachedProductionSha = (git -C $ProductionRoot rev-parse HEAD).Trim()
$CachedProductionDirty = @(git -C $ProductionRoot status --porcelain)
if ($CachedProductionSha -ne $PRODUCTION_SHA) {
    throw "Pinned production donor checkout moved during Monster execution."
}
if ($CachedProductionDirty.Count -ne 0) {
    throw "Pinned production donor checkout was modified during Monster execution."
}
Write-Host "Production donor immutability: VERIFIED" -ForegroundColor DarkGray

$BusinessBrainObserved = (git -C $BusinessBrainRoot rev-parse HEAD).Trim()
$MoonSourceObserved = (git -C $MoonSourceRoot rev-parse HEAD).Trim()
$HzkObserved = (git -C $HzkRoot rev-parse HEAD).Trim()
$V5Observed = (git -C $V5Root rev-parse HEAD).Trim()
if ($BusinessBrainObserved -ne $BUSINESS_BRAIN_SHA) {
    throw "Pinned Business Brain checkout moved during Monster execution."
}
if ($MoonSourceObserved -ne $MOON_SOURCE_SHA) {
    throw "Pinned Moon Source checkout moved during Monster execution."
}
if ($HzkObserved -ne $HZK_SHA) {
    throw "Pinned HZK treaty checkout moved during Monster execution."
}
if ($V5Observed -ne $V5_SHA) {
    throw "Pinned V5 acceptance checkout moved during Monster execution."
}
if (@(git -C $BusinessBrainRoot status --porcelain).Count -ne 0) {
    throw "Pinned Business Brain checkout was modified during Monster execution."
}
if (@(git -C $MoonSourceRoot status --porcelain).Count -ne 0) {
    throw "Pinned Moon Source checkout was modified during Monster execution."
}
if (@(git -C $HzkRoot status --porcelain).Count -ne 0) {
    throw "Pinned HZK treaty checkout was modified during Monster execution."
}
if (@(git -C $V5Root status --porcelain).Count -ne 0) {
    throw "Pinned V5 acceptance checkout was modified during Monster execution."
}
Write-Host "Attribution / HZK / V5 source immutability: VERIFIED" -ForegroundColor DarkGray

$TaktMarkdown = Join-Path $ArtifactRoot "TAKT_TIMINGS.md"
$TaktJson = Join-Path $ArtifactRoot "takt-timings.json"
if (Test-Path $TaktMarkdown -PathType Leaf) {
    Write-Host "TAKT report:     $TaktMarkdown" -ForegroundColor Cyan
}
if (Test-Path $TaktJson -PathType Leaf) {
    Write-Host "TAKT raw JSON:   $TaktJson" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
if ($ExitCode -eq 0) {
    Write-Host " ATTRIBUTION + TAKT MONSTER CAMPAIGN: GREEN" -ForegroundColor Green
} else {
    Write-Host " ATTRIBUTION + TAKT MONSTER CAMPAIGN: RED ($ExitCode)" -ForegroundColor Red
}
Write-Host " Classification: ISOLATED USER18 / ATTRIBUTION COMPOSITION / TAKT OBSERVATION" -ForegroundColor Yellow
Write-Host " Evidence mode: $EvidenceMode" -ForegroundColor Yellow
Write-Host " Evidence/state: $RunRoot" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

exit $ExitCode
