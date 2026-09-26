$helperPath = Join-Path $PSScriptRoot '../launch_helpers.ps1'
. $helperPath

Describe 'Invoke-QuietNative' {
    It 'does not stop when a successful native command writes progress to stderr' {
        $previousPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Stop'
            $exitCode = Invoke-QuietNative -FilePath $env:ComSpec -Arguments @(
                '/d', '/c', 'echo Container backend Running 1>&2 & exit /b 0'
            )
            $exitCode | Should Be 0
        } finally {
            $ErrorActionPreference = $previousPreference
        }
    }

    It 'returns a nonzero native exit code for the caller to handle' {
        $exitCode = Invoke-QuietNative -FilePath $env:ComSpec -Arguments @('/d', '/c', 'exit /b 7')
        $exitCode | Should Be 7
    }
}

Describe 'Read-CopilotKeyFile' {
    It 'reads only a literal key from a file outside the repository' {
        $path = Join-Path $TestDrive 'copilot.env'
        [System.IO.File]::WriteAllText($path, "LLM_API_KEY=fake-local-test-key`n")
        $forbidden = Join-Path $TestDrive 'repository'
        Read-CopilotKeyFile -Path $path -ForbiddenRoot $forbidden |
            Should Be 'fake-local-test-key'
    }

    It 'rejects a file inside the repository' {
        $path = Join-Path $TestDrive 'copilot.env'
        [System.IO.File]::WriteAllText($path, "LLM_API_KEY=fake-local-test-key`n")
        $threw = $false
        try { Read-CopilotKeyFile -Path $path -ForbiddenRoot $TestDrive | Out-Null }
        catch { $threw = $true }
        $threw | Should Be $true
    }

    It 'rejects shell syntax without executing it' {
        $path = Join-Path $TestDrive 'copilot.env'
        $marker = Join-Path $TestDrive 'executed.txt'
        [System.IO.File]::WriteAllText(
            $path, ('LLM_API_KEY=$(Set-Content -LiteralPath "{0}" -Value yes)' -f $marker)
        )
        $forbidden = Join-Path $TestDrive 'repository'
        $threw = $false
        try { Read-CopilotKeyFile -Path $path -ForbiddenRoot $forbidden | Out-Null }
        catch { $threw = $true }
        $threw | Should Be $true
        Test-Path -LiteralPath $marker | Should Be $false
    }

    It 'rejects additional settings and duplicate keys' {
        $path = Join-Path $TestDrive 'copilot.env'
        [System.IO.File]::WriteAllText(
            $path, "LLM_API_KEY=fake-key`nCOPILOT_ENABLED=true`nLLM_API_KEY=duplicate`n"
        )
        $forbidden = Join-Path $TestDrive 'repository'
        $threw = $false
        try { Read-CopilotKeyFile -Path $path -ForbiddenRoot $forbidden | Out-Null }
        catch { $threw = $true }
        $threw | Should Be $true
    }
}
