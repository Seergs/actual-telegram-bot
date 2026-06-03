# actual-telegram-bot

Telegram bot to add transactions to Actual Budget from a text message.

## Usage

Send a message in this format:

```
<payee> <amount> [account] [date]
```

Examples:

```
starbucks 80
netflix 120 credit
uber 145 yesterday
rent 12000 debito lunes
gasoline 500 28/05
```

The bot fuzzy-matches your input against your Actual payees. If there is a clear match it inserts directly; if ambiguous, it shows you options to choose from.

### Account

Optionally specify an account inline as the last or second-to-last token. The bot fuzzy-matches against your Actual account names, so partial names work (e.g. `debito`, `credit`, `2`).

### Date

Optionally specify a date as the last token. Supported values:

- `today` / `hoy`
- `yesterday` / `ayer`
- Day name: `monday`–`sunday` / `lunes`–`domingo` (resolves to the most recent occurrence)
- `DD/MM` (e.g. `28/05`)

If omitted, defaults to today.

## Commands

- `/start` — show usage instructions
- `/account` — view or change the active account for the session
- `/accounts` — list available accounts
- `/refresh` — refresh the payees cache

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```
TELEGRAM_TOKEN=
TELEGRAM_ALLOWED_USER_ID=
ACTUAL_SERVER_URL=
ACTUAL_API_KEY=
ACTUAL_BUDGET_ID=
ACTUAL_ACCOUNT_DEFAULT=   # optional, defaults to first account
```

## Running locally

```
docker build -t actual-telegram-bot .
docker run --env-file .env actual-telegram-bot
```
