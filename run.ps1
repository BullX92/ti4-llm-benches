[CmdletBinding()]
param(
    [string]$PythonCommand,
    [string]$BindHost,
    [int]$Port,
    [int]$PromptfooViewPort,
    [switch]$CheckOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Status {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    Write-Host ("[run.ps1] {0}" -f $Message)
}

function Resolve-PythonCommandParts {
    param(
        [string]$RequestedCommand
    )

    if ($RequestedCommand) {
        return @($RequestedCommand)
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @($python.Source)
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        return @($pyLauncher.Source, '-3')
    }

    throw 'Python was not found. Install Python or pass -PythonCommand explicitly.'
}

function Test-CommandAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandName,

        [Parameter(Mandatory = $true)]
        [string]$InstallHint
    )

    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "$CommandName was not found. $InstallHint"
    }
}

$repoRoot = $PSScriptRoot
$pythonParts = @(Resolve-PythonCommandParts -RequestedCommand $PythonCommand)
$serverPath = Join-Path $repoRoot 'testpipeline\server.py'
$envPath = Join-Path $repoRoot '.env'
$effectiveHost = if ($PSBoundParameters.ContainsKey('BindHost')) { $BindHost } elseif ($env:BIND_HOST) { $env:BIND_HOST } else { '127.0.0.1' }
$effectivePort = if ($PSBoundParameters.ContainsKey('Port')) { $Port } elseif ($env:PORT) { [int]$env:PORT } else { 8642 }
$effectiveViewPort = if ($PSBoundParameters.ContainsKey('PromptfooViewPort')) { $PromptfooViewPort } elseif ($env:PROMPTFOO_VIEW_PORT) { [int]$env:PROMPTFOO_VIEW_PORT } else { 9119 }

if (-not (Test-Path $serverPath)) {
    throw "Pipeline entry point not found: $serverPath"
}

Write-Status 'Checking local prerequisites...'
Test-CommandAvailable -CommandName 'node' -InstallHint 'Install Node.js so npx can run promptfoo.'
Test-CommandAvailable -CommandName 'npx' -InstallHint 'Install Node.js so promptfoo can be launched with npx.'

Write-Status ("Repo root: {0}" -f $repoRoot)
Write-Status ("Python: {0}" -f ($pythonParts -join ' '))
Write-Status ("Server: {0}" -f $serverPath)

if (Test-Path $envPath) {
    Write-Status '.env: found'
}
else {
    Write-Warning '.env not found. The server can still start, but provider bootstrap may be incomplete.'
}

Write-Status ("UI URL: http://{0}:{1}" -f $effectiveHost, $effectivePort)
Write-Status ("Promptfoo viewer target port: {0}" -f $effectiveViewPort)

$previousHost = $null
$previousPort = $null
$previousViewPort = $null

if ($PSBoundParameters.ContainsKey('BindHost')) {
    $previousHost = [Environment]::GetEnvironmentVariable('BIND_HOST', 'Process')
    [Environment]::SetEnvironmentVariable('BIND_HOST', $BindHost, 'Process')
}

if ($PSBoundParameters.ContainsKey('Port')) {
    $previousPort = [Environment]::GetEnvironmentVariable('PORT', 'Process')
    [Environment]::SetEnvironmentVariable('PORT', [string]$Port, 'Process')
}

if ($PSBoundParameters.ContainsKey('PromptfooViewPort')) {
    $previousViewPort = [Environment]::GetEnvironmentVariable('PROMPTFOO_VIEW_PORT', 'Process')
    [Environment]::SetEnvironmentVariable('PROMPTFOO_VIEW_PORT', [string]$PromptfooViewPort, 'Process')
}

$launchArgs = @('testpipeline/server.py')
$pythonExe = $pythonParts[0]
$pythonArgs = @()
if ($pythonParts.Length -gt 1) {
    $pythonArgs += $pythonParts[1..($pythonParts.Length - 1)]
}
$pythonArgs += $launchArgs

Write-Status 'Switching to repo root and preparing server process...'
Push-Location $repoRoot
try {
    if ($CheckOnly) {
        Write-Status 'Prerequisite check passed. Server was not started because -CheckOnly was supplied.'
        return
    }

    if ($PSBoundParameters.ContainsKey('BindHost')) {
        Write-Status "BIND_HOST override: $BindHost"
    }
    if ($PSBoundParameters.ContainsKey('Port')) {
        Write-Status "PORT override: $Port"
    }
    if ($PSBoundParameters.ContainsKey('PromptfooViewPort')) {
        Write-Status "PROMPTFOO_VIEW_PORT override: $PromptfooViewPort"
    }

    Write-Status 'Starting benchmark pipeline. Press Ctrl+C to stop the server.'
    & $pythonExe @pythonArgs
}
finally {
    Pop-Location
    Write-Status 'Returned to previous working directory.'

    if ($PSBoundParameters.ContainsKey('BindHost')) {
        [Environment]::SetEnvironmentVariable('BIND_HOST', $previousHost, 'Process')
    }
    if ($PSBoundParameters.ContainsKey('Port')) {
        [Environment]::SetEnvironmentVariable('PORT', $previousPort, 'Process')
    }
    if ($PSBoundParameters.ContainsKey('PromptfooViewPort')) {
        [Environment]::SetEnvironmentVariable('PROMPTFOO_VIEW_PORT', $previousViewPort, 'Process')
    }
}