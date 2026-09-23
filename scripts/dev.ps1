$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

$uvExecutable = (Get-Command uv -ErrorAction Stop).Source
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($null -eq $npmCommand) {
    $npmCommand = Get-Command npm -ErrorAction Stop
}

$children = @()

function Stop-ChildProcess {
    param([System.Diagnostics.Process]$Process)

    if ($null -ne $Process -and -not $Process.HasExited) {
        $Process.Kill($true)
        $Process.WaitForExit()
    }
}

try {
    $children += Start-Process `
        -FilePath $uvExecutable `
        -ArgumentList @(
            "run", "--directory", "backend", "fastapi", "dev",
            "app/main.py", "--port", "8000"
        ) `
        -NoNewWindow `
        -PassThru

    $children += Start-Process `
        -FilePath $npmCommand.Source `
        -ArgumentList @("--prefix", "frontend", "run", "dev") `
        -NoNewWindow `
        -PassThru

    Write-Host "Tirke is starting:"
    Write-Host "  Web: http://localhost:3000"
    Write-Host "  API: http://localhost:8000/docs"
    Write-Host "Press Ctrl+C to stop both services."

    while (($children | Where-Object { -not $_.HasExited }).Count -eq 2) {
        Start-Sleep -Milliseconds 500
    }

    $failed = $children | Where-Object { $_.HasExited -and $_.ExitCode -ne 0 }
    if ($failed) {
        throw "A development service stopped unexpectedly."
    }
}
finally {
    foreach ($child in $children) {
        Stop-ChildProcess -Process $child
    }
}
