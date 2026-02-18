param(
  [string]$BackendUrl = "",
  [string]$SimulatorUrl = "",
  [string]$FrontendUrl = "",
  [switch]$AllowAllCors
)

$ErrorActionPreference = "Stop"

function Normalize-Url([string]$u) {
  if (-not $u) { return "" }
  $u = $u.Trim()
  if ($u.EndsWith('/')) { $u = $u.Substring(0, $u.Length - 1) }
  return $u
}

function New-RandomKey([int]$len = 40) {
  $chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
  $bytes = New-Object byte[] $len
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $sb = New-Object System.Text.StringBuilder
  foreach ($b in $bytes) {
    [void]$sb.Append($chars[$b % $chars.Length])
  }
  return $sb.ToString()
}

if (-not $SimulatorUrl) {
  $SimulatorUrl = Read-Host "Simulator public URL (example: https://sim-xxxx.abrhaas.com)"
}
if (-not $BackendUrl) {
  $BackendUrl = Read-Host "Backend public URL (example: https://api-xxxx.abrhaas.com)"
}
if (-not $AllowAllCors -and -not $FrontendUrl) {
  $FrontendUrl = Read-Host "Frontend public URL (or press Enter to use *)"
}

$BackendUrl = Normalize-Url $BackendUrl
$SimulatorUrl = Normalize-Url $SimulatorUrl
$FrontendUrl = Normalize-Url $FrontendUrl

if (-not $BackendUrl) { throw "Backend URL is required" }
if (-not $SimulatorUrl) { throw "Simulator URL is required" }

if ($AllowAllCors -or -not $FrontendUrl) {
  $cors = "*"
} else {
  $cors = "$FrontendUrl,http://localhost:3000"
}

$adminKey = New-RandomKey 48
$operatorKey = New-RandomKey 48
$monitorKey = New-RandomKey 48

New-Item -ItemType Directory -Force deployment | Out-Null

$backendEnv = @"
ROBOT_IDS=SIM-ROBOT-1,SIM-ROBOT-2
SAFE_MODE=0
AUTOX_FORCE_ENV=1
AUTOX_BASE_URL=$SimulatorUrl
AUTOX_APP_ID=mock
AUTOX_APP_SECRET=mock
AUTOX_APP_CODE=mock
CORS_ALLOW_ORIGINS=$cors
CORS_ALLOW_CREDENTIALS=0
AUTO_TICK_ENABLED=0
AUTO_CONFIRM_ENABLED=0
ALLOW_DEFAULT_API_KEYS=0
"@

$backendSecrets = @"
API_KEY_ADMIN=$adminKey
API_KEY_OPERATOR=$operatorKey
API_KEY_MONITOR=$monitorKey
"@

$simEnv = @"
SIM_APP_BASE_URL=$BackendUrl
"@

$simSecrets = @"
SIM_API_KEY=$adminKey
"@

Set-Content -Path deployment/backend.ready.env -Value $backendEnv -Encoding UTF8
Set-Content -Path deployment/backend.secrets.ready.env -Value $backendSecrets -Encoding UTF8
Set-Content -Path deployment/simulator.ready.env -Value $simEnv -Encoding UTF8
Set-Content -Path deployment/simulator.secrets.ready.env -Value $simSecrets -Encoding UTF8

Write-Host "Generated files:"
Write-Host " - deployment/backend.ready.env"
Write-Host " - deployment/backend.secrets.ready.env"
Write-Host " - deployment/simulator.ready.env"
Write-Host " - deployment/simulator.secrets.ready.env"
Write-Host ""
Write-Host "Use these values in frontend header: X-API-Key = $adminKey"
