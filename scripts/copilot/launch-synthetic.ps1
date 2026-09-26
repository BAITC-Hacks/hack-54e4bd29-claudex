param(
    [Parameter(Mandatory = $true)]
    [string]$AcceptanceDir,
    [switch]$Restore,
    [switch]$PrepareOnly,
    [string]$CopilotEnvPath
)

$ErrorActionPreference = 'Stop'
$copilotRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $PSScriptRoot 'launch_helpers.ps1')
$acceptancePath = (Resolve-Path -LiteralPath $AcceptanceDir).Path
$manifestPath = Join-Path $acceptancePath 'manifest.json'
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.project -notmatch '^phase8-[a-z0-9-]+$' -or
    $manifest.origin -notmatch '^http://127\.0\.0\.1:[0-9]+$') {
    throw 'Only a loopback phase8 synthetic acceptance project is supported.'
}

$acceptanceRoot = (Resolve-Path (Join-Path $acceptancePath '../../..')).Path
$baseCompose = Join-Path $acceptanceRoot 'docker-compose.yml'
$acceptanceCompose = Join-Path $acceptancePath 'compose.override.yml'
$acceptanceEnv = Join-Path $acceptancePath '.env'
foreach ($path in @($baseCompose, $acceptanceCompose, $acceptanceEnv)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw 'Synthetic acceptance configuration is incomplete.'
    }
}

if ($Restore) {
    $restoreArgs = @(
        'compose', '--project-name', $manifest.project,
        '--env-file', $acceptanceEnv,
        '--file', $baseCompose,
        '--file', $acceptanceCompose,
        'up', '-d', '--no-deps', '--force-recreate', 'backend'
    )
    $restoreExitCode = Invoke-QuietNative -FilePath 'docker' -Arguments $restoreArgs
    if ($restoreExitCode -ne 0) { throw 'Synthetic backend restore failed.' }
    Write-Output 'Synthetic backend restored without Copilot key.'
    return
}

# The generated overlay contains only variable references and one read-only code mount.
# The API key is entered below and exists only in the launcher/backend process environment.
$localDir = Join-Path $copilotRoot 'tmp/copilot-demo'
New-Item -ItemType Directory -Path $localDir -Force | Out-Null
$overlayPath = Join-Path $localDir 'compose.override.yml'
$backendPath = (Resolve-Path (Join-Path $copilotRoot 'backend')).Path.Replace('\', '/')
$backendMount = ('{0}:/app:ro' -f $backendPath) | ConvertTo-Json -Compress
$overlay = @"
services:
  backend:
    volumes: !override
      - $backendMount
    environment:
      COPILOT_ENABLED: `${COPILOT_ENABLED:?required}
      LLM_PROVIDER: `${LLM_PROVIDER:?required}
      LLM_MODEL: `${LLM_MODEL:?required}
      LLM_TIMEOUT_SECONDS: `${LLM_TIMEOUT_SECONDS:?required}
      LLM_MAX_OUTPUT_TOKENS: `${LLM_MAX_OUTPUT_TOKENS:?required}
      LLM_API_KEY: `${LLM_API_KEY:?required}
"@
[System.IO.File]::WriteAllText($overlayPath, $overlay, [System.Text.UTF8Encoding]::new($false))
if ($PrepareOnly) {
    Write-Output 'Secret-free synthetic backend overlay prepared; no container was changed.'
    return
}

$secret = $null
$ptr = [IntPtr]::Zero
try {
    if ($CopilotEnvPath) {
        $commonDir = @(& git -C $copilotRoot rev-parse --git-common-dir 2>$null)[0]
        if ($LASTEXITCODE -ne 0 -or -not $commonDir) {
            throw 'Cannot determine repository boundary for local key file.'
        }
        if (-not [System.IO.Path]::IsPathRooted($commonDir)) {
            $commonDir = Join-Path $copilotRoot $commonDir
        }
        $repositoryRoot = Split-Path -Parent ([System.IO.Path]::GetFullPath($commonDir))
        $env:LLM_API_KEY = Read-CopilotKeyFile -Path $CopilotEnvPath -ForbiddenRoot $repositoryRoot
    } else {
        $secret = Read-Host 'OpenAI API key (hidden input)' -AsSecureString
        if ($null -eq $secret -or $secret.Length -eq 0) {
            throw 'Key was not provided; no backend was changed.'
        }
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
        $env:LLM_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    $env:COPILOT_ENABLED = 'true'
    $env:LLM_PROVIDER = 'openai'
    $env:LLM_MODEL = 'gpt-4.1-mini-2025-04-14'
    $env:LLM_TIMEOUT_SECONDS = '30'
    $env:LLM_MAX_OUTPUT_TOKENS = '1200'

    $composeArgs = @(
        'compose', '--project-name', $manifest.project,
        '--env-file', $acceptanceEnv,
        '--file', $baseCompose,
        '--file', $acceptanceCompose,
        '--file', $overlayPath,
        'up', '-d', '--no-deps', 'backend'
    )
    # Do not echo rendered Compose config, process environment or raw Docker output.
    $composeExitCode = Invoke-QuietNative -FilePath 'docker' -Arguments $composeArgs
    if ($composeExitCode -ne 0) {
        throw 'Backend recreation failed; inspect local Docker state privately.'
    }
    $healthy = $false
    for ($attempt = 0; $attempt -lt 12; $attempt++) {
        try {
            $health = Invoke-WebRequest -Uri ($manifest.origin + '/api/v1/health') -UseBasicParsing -TimeoutSec 5
            if ($health.StatusCode -eq 200) { $healthy = $true; break }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    if (-not $healthy) { throw 'Backend health check failed.' }
    Write-Output ('Synthetic backend ready at {0}; no LLM request has been sent.' -f $manifest.origin)
} finally {
    Remove-Item Env:LLM_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:COPILOT_ENABLED -ErrorAction SilentlyContinue
    Remove-Item Env:LLM_PROVIDER -ErrorAction SilentlyContinue
    Remove-Item Env:LLM_MODEL -ErrorAction SilentlyContinue
    Remove-Item Env:LLM_TIMEOUT_SECONDS -ErrorAction SilentlyContinue
    Remove-Item Env:LLM_MAX_OUTPUT_TOKENS -ErrorAction SilentlyContinue
    if ($ptr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
    if ($null -ne $secret) { $secret.Dispose() }
}
