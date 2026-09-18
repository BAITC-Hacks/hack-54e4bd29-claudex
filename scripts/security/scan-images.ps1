param(
    [string]$Output = "artifacts/phase8-security/image-scan.json",
    [string[]]$Images = @(
        "medsignal-backend:latest",
        "medsignal-frontend:latest",
        "medsignal-worker:latest",
        "medsignal-mlflow:latest",
        "nginx:1.30.5-alpine@sha256:f2e97a6801f504129e8027ff7d49e27fa59ef4f1ebfd97197dac8b194831cf3d"
    )
)

$ErrorActionPreference = "Stop"
$trivy = "aquasec/trivy:0.58.2"
$target = [System.IO.Path]::GetFullPath($Output)
$directory = Split-Path -Parent $target
New-Item -ItemType Directory -Force -Path $directory | Out-Null

$results = @()
foreach ($image in $Images) {
    $raw = docker run --rm `
        -v //var/run/docker.sock:/var/run/docker.sock `
        -v phase8-trivy-cache:/root/.cache/trivy `
        $trivy image --scanners vuln --severity HIGH,CRITICAL --format json $image
    if ($LASTEXITCODE -ne 0) { throw "Trivy failed for $image" }
    $parsed = $raw | ConvertFrom-Json
    $high = 0
    $critical = 0
    $fixableHigh = 0
    $fixableCritical = 0
    foreach ($result in $parsed.Results) {
        foreach ($item in $result.Vulnerabilities) {
            if ($item.Severity -eq "HIGH") { $high++ }
            if ($item.Severity -eq "CRITICAL") { $critical++ }
            if ($item.FixedVersion) {
                if ($item.Severity -eq "HIGH") { $fixableHigh++ }
                if ($item.Severity -eq "CRITICAL") { $fixableCritical++ }
            }
        }
    }
    $inspect = docker image inspect $image | ConvertFrom-Json
    $results += [ordered]@{
        image = $image
        digest = $inspect[0].Id
        high = $high
        critical = $critical
        fixable_high = $fixableHigh
        fixable_critical = $fixableCritical
    }
}

[ordered]@{
    scanner = $trivy
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    images = $results
} | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 $target

Get-Content $target
