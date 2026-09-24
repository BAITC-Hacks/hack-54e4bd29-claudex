param(
    [string]$Python = "python",
    [string]$Output = "artifacts/phase8-security/image-scan.json",
    [string[]]$Images = @(
        "medsignal-backend:ci",
        "medsignal-frontend:ci",
        "medsignal-worker:ci",
        "medsignal-mlflow:ci",
        "nginx:1.30.5-alpine@sha256:f2e97a6801f504129e8027ff7d49e27fa59ef4f1ebfd97197dac8b194831cf3d"
    )
)

$ErrorActionPreference = "Stop"
$arguments = @("-m", "scripts.security.image_scan", "--output", $Output)
foreach ($image in $Images) { $arguments += @("--image", $image) }
& $Python @arguments
exit $LASTEXITCODE
