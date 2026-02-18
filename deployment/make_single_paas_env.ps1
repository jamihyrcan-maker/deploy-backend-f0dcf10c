param(
  [string]$BackendUrl = "",
  [string]$SimulatorUrl = "",
  [string]$FrontendUrl = ""
)

$ErrorActionPreference = "Stop"

function Normalize-Url([string]$u) {
  if (-not $u) { return "" }
  $u = $u.Trim()
  if ($u.EndsWith('/')) { $u = $u.Substring(0, $u.Length - 1) }
  return $u
}

function New-RandomKey([int]$len = 48) {
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
  $SimulatorUrl = Read-Host "Simulator public URL (https://...)"
}
if (-not $BackendUrl) {
  $BackendUrl = Read-Host "Backend public URL (https://...)"
}
if (-not $FrontendUrl) {
  $FrontendUrl = Read-Host "Frontend public URL (https://...) or *"
}

$BackendUrl = Normalize-Url $BackendUrl
$SimulatorUrl = Normalize-Url $SimulatorUrl
$FrontendUrl = Normalize-Url $FrontendUrl

if (-not $BackendUrl) { throw "Backend URL is required" }
if (-not $SimulatorUrl) { throw "Simulator URL is required" }
if (-not $FrontendUrl) { $FrontendUrl = "*" }

$cors = if ($FrontendUrl -eq "*") { "*" } else { "$FrontendUrl,http://localhost:3000" }

$adminKey = New-RandomKey
$operatorKey = New-RandomKey
$monitorKey = New-RandomKey

New-Item -ItemType Directory -Force deployment | Out-Null

$single = @"
ROBOT_IDS=SIM-ROBOT-1,SIM-ROBOT-2
SAFE_MODE=0
AUTOX_FORCE_ENV=1
AUTOX_BASE_URL=$SimulatorUrl
AUTOX_APP_ID=mock
AUTOX_APP_SECRET=mock
AUTOX_APP_CODE=mock

API_KEY_ADMIN=$adminKey
API_KEY_OPERATOR=$operatorKey
API_KEY_MONITOR=$monitorKey

CORS_ALLOW_ORIGINS=$cors
CORS_ALLOW_CREDENTIALS=0
AUTO_TICK_ENABLED=0
AUTO_CONFIRM_ENABLED=0
ALLOW_DEFAULT_API_KEYS=0

SIM_APP_BASE_URL=$BackendUrl
SIM_API_KEY=$adminKey
"@

Set-Content -Path deployment/paas.single.ready.env -Value $single -Encoding UTF8

Write-Host "Generated: deployment/paas.single.ready.env"
Write-Host "Frontend header X-API-Key: $adminKey"
