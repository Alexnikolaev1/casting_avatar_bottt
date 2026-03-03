# 🎭 Твой личный кастинг — Telegram Bot

Telegram-бот для создания стилизованных портретов с помощью YandexART.

## Стэк

- **Python 3.11+** + aiogram 3.x
- **Vercel** — serverless деплой
- **PostgreSQL** (Vercel Postgres) — база данных
- **Vercel KV** (Redis) — очередь задач
- **Vercel Blob** — хранение изображений
- **YandexART** — генерация изображений
- **ЮKassa** — приём платежей

## Быстрый старт

### 1. Клонирование и зависимости

```bash
git clone <repo>
cd casting_bot
pip install -r requirements.txt
```

### 2. Настройка переменных окружения

```bash
cp .env.example .env
# Заполни все переменные в .env
```

### 3. Инициализация БД

```bash
python scripts/init_db.py
```

### 4. Локальный запуск (для разработки)

```bash
python scripts/run_local.py
```

### 5. Тест генерации

```bash
python scripts/test_generation.py cyberpunk
```

### 6. Деплой на Vercel

```bash
npm i -g vercel
vercel login
vercel --prod
```

### 7. Установка webhook

```bash
export VERCEL_URL=https://your-project.vercel.app
bash scripts/setup_webhook.sh
```

## Структура проекта

```
casting_bot/
├── api/
│   ├── webhook.py          # Telegram webhook
│   ├── payment_webhook.py  # ЮKassa webhook
│   └── worker.py           # Cron-воркер генераций
├── bot/
│   ├── config.py           # Конфигурация
│   ├── database.py         # Работа с PostgreSQL
│   ├── app.py              # Главный роутер
│   ├── routers/            # Разделенные роутеры (user/admin)
│   ├── keyboards.py        # Inline-клавиатуры
│   ├── storage.py          # Blob + KV (Redis)
│   ├── styles.py           # Стили и промты
│   ├── ui.py               # Форматтеры UI-текста
│   ├── texts.py            # Тексты интерфейса
│   ├── worker.py           # Логика воркера
│   └── yandex_art.py       # YandexART API
├── scripts/
│   ├── init_db.py
│   ├── run_local.py
│   ├── setup_webhook.sh
│   └── test_generation.py
├── .env.example
├── requirements.txt
└── vercel.json
```

## Переменные окружения

| Переменная | Описание |
|---|---|
| BOT_TOKEN | Токен от @BotFather |
| WEBHOOK_SECRET | Случайная строка для защиты webhook |
| BOT_USERNAME | Username бота без @ |
| YANDEX_API_KEY | API-ключ сервисного аккаунта Yandex |
| YANDEX_FOLDER_ID | ID каталога Yandex Cloud |
| YUKASSA_SHOP_ID | ID магазина ЮKassa |
| YUKASSA_SECRET_KEY | Секретный ключ ЮKassa |
| DATABASE_URL | Строка подключения PostgreSQL |
| KV_REST_API_URL | URL Vercel KV |
| KV_REST_API_TOKEN | Токен Vercel KV |
| BLOB_READ_WRITE_TOKEN | Токен Vercel Blob |
| CRON_SECRET | Секрет для защиты cron-endpoint |
| ADMIN_IDS | Telegram ID администраторов через запятую |

## Монетизация

- Первые 2 генерации — бесплатно
- 20 руб. — один образ
- 100 руб. — премиум-пакет из 5 образов

## Реферальная программа

- Пригласил друга → +1 бесплатная генерация
- Пришёл по ссылке → скидка 50% на первый образ
