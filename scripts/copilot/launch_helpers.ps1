function Invoke-QuietNative {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    # Docker Compose writes normal progress messages to stderr. In PowerShell
    # with ErrorActionPreference=Stop, that stream becomes NativeCommandError
    # before the caller can check Docker's actual exit status.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $FilePath @Arguments 2>&1 | Out-Null
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Read-CopilotKeyFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$ForbiddenRoot
    )

    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($item.PSIsContainer -or $item.Name -cne 'copilot.env' -or
        ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -or
        $item.Length -gt 4096) {
        throw 'Invalid local Copilot key file.'
    }

    $fullPath = [System.IO.Path]::GetFullPath($item.FullName)
    $root = [System.IO.Path]::GetFullPath($ForbiddenRoot).TrimEnd('\', '/')
    $rootPrefix = $root + [System.IO.Path]::DirectorySeparatorChar
    if ($fullPath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or
        [string]::Equals($fullPath, $root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Local Copilot key file must be outside the repository and build context.'
    }

    # Treat the file as literal data. Never dot-source, Invoke-Expression or expand it.
    $lines = @([System.IO.File]::ReadAllLines($fullPath, [System.Text.Encoding]::UTF8) |
        Where-Object { $_.Trim() -ne '' -and -not $_.TrimStart().StartsWith('#') })
    if ($lines.Count -ne 1 -or $lines[0] -cnotmatch '^LLM_API_KEY=([A-Za-z0-9._-]+)$') {
        throw 'Local Copilot key file must contain only one literal LLM_API_KEY assignment.'
    }
    return $matches[1]
}
