[CmdletBinding()]
param(
    [int]$ViewPort = 15500,
    [int]$StartupDelaySeconds = 3
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Status {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    Write-Host ("[bench-and-view.ps1] {0}" -f $Message)
}

function Assert-Command {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$InstallHint
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name was not found. $InstallHint"
    }
}

function Invoke-Bench {
    Write-Status 'Running benchmark...'
    & npm run bench | Out-Host
    return [int]$LASTEXITCODE
}

function Backup-PromptfooDb {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ConfigDir
    )

    $dbPath = Join-Path $ConfigDir 'promptfoo.db'
    if (-not (Test-Path $dbPath)) {
        return $false
    }

    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backupPath = Join-Path $ConfigDir ("promptfoo.db.bak-{0}" -f $timestamp)
    Move-Item -LiteralPath $dbPath -Destination $backupPath
    Write-Status ("Backed up broken Promptfoo DB to {0}" -f $backupPath)
    return $true
}

function Test-BenchExitCodeSuccess {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ExitCode
    )

    return $ExitCode -eq 0 -or $ExitCode -eq 100
}

$repoRoot = $PSScriptRoot
$envPath = Join-Path $repoRoot '.env'
$promptfooConfigDir = Join-Path $repoRoot '.promptfoo'
$viewUrl = "http://localhost:$ViewPort"

Assert-Command -Name 'node' -InstallHint 'Install Node.js.'
Assert-Command -Name 'npm' -InstallHint 'Install Node.js and npm.'

if (-not (Test-Path $envPath)) {
    throw ".env not found at $envPath"
}

if (-not (Test-Path $promptfooConfigDir)) {
    New-Item -ItemType Directory -Path $promptfooConfigDir | Out-Null
}

Push-Location $repoRoot
try {
    $env:PROMPTFOO_CONFIG_DIR = '.promptfoo'

    $benchExitCode = Invoke-Bench
    if (-not (Test-BenchExitCodeSuccess -ExitCode $benchExitCode)) {
        Write-Status ("First bench run failed with exit code {0}" -f $benchExitCode)
        $didBackupDb = Backup-PromptfooDb -ConfigDir $promptfooConfigDir
        if ($didBackupDb) {
            Write-Status 'Retrying benchmark with a fresh Promptfoo DB...'
            $benchExitCode = Invoke-Bench
        }
    }

    if (-not (Test-BenchExitCodeSuccess -ExitCode $benchExitCode)) {
        throw "npm run bench failed with exit code $benchExitCode"
    }

    Write-Status 'Starting Promptfoo view server in the background...'
    $viewProcess = Start-Process `
        -FilePath 'npm.cmd' `
        -ArgumentList @('run', 'view') `
        -WorkingDirectory $repoRoot `
        -WindowStyle Hidden `
        -PassThru

    Start-Sleep -Seconds $StartupDelaySeconds

    Write-Status ("Opening browser: {0}" -f $viewUrl)
    Start-Process $viewUrl | Out-Null

    Write-Status ("Promptfoo view is running in the background (PID {0})." -f $viewProcess.Id)
}
finally {
    Pop-Location
}
