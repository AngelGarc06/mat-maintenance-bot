param([string]$Token = $env:TELEGRAM_BOT_TOKEN)

if (-not $Token) {
  throw "No hay token. Pasa -Token <BOT_TOKEN> o define $env:TELEGRAM_BOT_TOKEN."
}

$info = Invoke-RestMethod -Uri ("https://api.telegram.org/bot{0}/getWebhookInfo" -f $Token)
$info | Format-List
