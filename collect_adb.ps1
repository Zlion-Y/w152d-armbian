param(
    [Parameter(Mandatory=$true)][string]$Serial,
    [string]$Adb = 'adb'
)
$ErrorActionPreference = 'Stop'
$taskOutput = Join-Path $PSScriptRoot 'evidence'
New-Item -ItemType Directory -Force -Path $taskOutput | Out-Null
# The caller connects the device first. Every adb operation targets one serial.
& $Adb -s $Serial get-state
if ($LASTEXITCODE -ne 0) { throw 'Target is not connected. Connect it before collecting.' }
$taskScript = Join-Path $PSScriptRoot 'src\collect_android.sh'
# Send the script over stdin; no device files are created.
$taskText = [IO.File]::ReadAllText($taskScript).Replace("`r`n", "`n")
$taskResult = $taskText | & $Adb -s $Serial shell sh 2>&1
$taskExit = $LASTEXITCODE
$taskLog = Join-Path $taskOutput ('android_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.txt')
$taskResult | Set-Content -LiteralPath $taskLog -Encoding utf8
Write-Output "Saved $taskLog"
if ($taskExit -ne 0) { throw "ADB collection exited with $taskExit; inspect the saved log." }
