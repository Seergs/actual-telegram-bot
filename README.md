# actual-telegram-bot

Telegram bot to add transactions to Actual Budget from a text message.

## Usage

Send a message in this format:

```
<payee> <amount>
```

Examples:

```
starbucks 80
netflix 120
uber 145
```

The bot fuzzy-matches your input against your Actual payees. If there is a clear match it inserts directly; if ambiguous, it shows you options to choose from.

## Commands

- `/start` — show usage instructions
- `/refresh` — refresh the payees cache

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```
TELEGRAM_TOKEN=
TELEGRAM_ALLOWED_USER_ID=
ACTUAL_SERVER_URL=
ACTUAL_API_KEY=
ACTUAL_BUDGET_ID=
ACTUAL_ACCOUNT_ID=
```

## Running locally

```
docker build -t actual-bot .
docker run --env-file .env actual-bot
```
