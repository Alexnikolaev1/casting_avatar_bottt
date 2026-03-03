#!/bin/bash
# Скрипт для установки webhook Telegram

# Загружаем переменные из .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

BOT_TOKEN=${BOT_TOKEN:?"BOT_TOKEN не задан"}
VERCEL_URL=${VERCEL_URL:?"VERCEL_URL не задан (например: https://your-project.vercel.app)"}
WEBHOOK_SECRET=${WEBHOOK_SECRET:?"WEBHOOK_SECRET не задан"}

WEBHOOK_URL="${VERCEL_URL}/api/webhook"

echo "Устанавливаем webhook: $WEBHOOK_URL"

curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"url\": \"${WEBHOOK_URL}\",
    \"secret_token\": \"${WEBHOOK_SECRET}\",
    \"allowed_updates\": [\"message\", \"callback_query\"],
    \"drop_pending_updates\": true
  }" | python3 -m json.tool

echo ""
echo "Проверка webhook:"
curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo" | python3 -m json.tool
