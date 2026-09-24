param(
    [string]$Python = "python",
    [string]$Output = "artifacts/phase8-security/image-scan.json",
    [string[]]$Images = @(
        "medsignal-backend:ci",
        "medsignal-frontend:ci",
        "medsignal-worker:ci",
        "medsignal-mlflow:ci",
        "medsignal-nginx:ci"
    )
)

$ErrorActionPreference = "Stop"
$arguments = @("-m", "scripts.security.image_scan", "--output", $Output)
foreach ($image in $Images) { $arguments += @("--image", $image) }
& $Python @arguments
exit $LASTEXITCODE
