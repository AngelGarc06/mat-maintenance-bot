Param(
  [string]$Token  = $env:TELEGRAM_BOT_TOKEN,
  [string]$Secret = $env:WEBHOOK_SECRET,
  [string]$Url    = ""
)

if (-not $Token)  { Write-Error "Falta TELEGRAM_BOT_TOKEN (env var) o pásalo con -Token";  exit 1 }
if (-not $Secret) { Write-Error "Falta WEBHOOK_SECRET (env var) o pásalo con -Secret";    exit 1 }

# Si no viene URL, intento tomarla de ngrok local (http://127.0.0.1:4040)
if (-not $Url) {
  try {
    $ng = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels"
    $pub = ($ng.tunnels | Where-Object { $_.proto -eq "https" }).public_url
    if ($pub) { $Url = "$pub/telegram/webhook" }
  } catch { }
}

if (-not $Url) {
  $Url = Read-Host "Pega la URL pública completa (ej: https://xxxxx.ngrok-free.app/telegram/webhook)"
}

$body = @{ url = $Url; secret_token = $Secret } | ConvertTo-Json
$res  = Invoke-RestMethod -Method Post `
        -Uri "https://api.telegram.org/bot$Token/setWebhook" `
        -ContentType "application/json" -Body $body

$res

# (Opcional) Verifica cómo quedó:
try {
  $info = Invoke-RestMethod -Uri "https://api.telegram.org/bot$Token/getWebhookInfo"
  "WebhookInfo:"
  $info
} catch { }
