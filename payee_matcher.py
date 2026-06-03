import unicodedata
import re
from datetime import date, timedelta
from rapidfuzz import process, fuzz

SCORE_AUTO = 80
SCORE_SUGGEST = 60

DATE_KEYWORDS = {
    "hoy", "ayer", "today", "yesterday",
    "lunes", "martes", "miercoles", "miércoles",
    "jueves", "viernes", "sabado", "sábado", "domingo",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
}

DAY_MAP = {
    "lunes": 0, "monday": 0,
    "martes": 1, "tuesday": 1,
    "miercoles": 2, "miércoles": 2, "wednesday": 2,
    "jueves": 3, "thursday": 3,
    "viernes": 4, "friday": 4,
    "sabado": 5, "sábado": 5, "saturday": 5,
    "domingo": 6, "sunday": 6
}

def normalize(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("utf-8").lower()

def is_date_token(token: str) -> bool:
    if normalize(token) in DATE_KEYWORDS:
        return True
    if re.match(r"^\d{1,2}/\d{1,2}$", token):
        return True
    return False

def resolve_date(token: str) -> str:
    n = normalize(token)
    today = date.today()

    if n in ("hoy", "today"):
        return today.isoformat()
    if n in ("ayer", "yesterday"):
        return (today - timedelta(days=1)).isoformat()

    if n in DAY_MAP:
        target = DAY_MAP[n]
        days_ago = (today.weekday() - target) % 7
        if days_ago == 0:
            days_ago = 7
        return (today - timedelta(days=days_ago)).isoformat()

    if re.match(r"^\d{1,2}/\d{1,2}$", token):
        day, month = map(int, token.split("/"))
        year = today.year
        try:
            d = date(year, month, day)
            if d > today:
                d = date(year - 1, month, day)
            return d.isoformat()
        except ValueError:
            pass

    return today.isoformat()

def match_payee(query: str, payees: list[dict]) -> dict:
    names = [p["name"] for p in payees if not p.get("transfer_acct")]

    for name in names:
        if name.lower() == query.lower():
            return {"type": "auto", "payee": name, "score": 100}

    result = process.extractOne(query, names, scorer=fuzz.WRatio)
    if not result:
        return {"type": "none"}

    name, score, _ = result

    if score >= SCORE_AUTO:
        return {"type": "auto", "payee": name, "score": score}
    elif score >= SCORE_SUGGEST:
        suggestions = process.extract(query, names, scorer=fuzz.WRatio, limit=3)
        return {"type": "suggest", "options": [s[0] for s in suggestions]}
    else:
        return {"type": "none", "query": query}

def parse_message_with_account(text: str, accounts: list[dict]) -> tuple[str, float, str | None, str | None, bool] | None:
    tokens = text.strip().split()
    if len(tokens) < 2:
        return None

    date_override = None
    account_override = None

    # 1. Check last token for date
    if len(tokens) >= 3 and is_date_token(tokens[-1]):
        date_override = resolve_date(tokens[-1])
        tokens = tokens[:-1]

    # 2. Check last token for account
    if len(tokens) >= 3:
        last = tokens[-1]
        is_number = last.isdigit()
        is_account = any(normalize(last) in normalize(a["name"]) for a in accounts)
        if is_number or is_account:
            try:
                float(tokens[-2].replace(",", ".").lstrip("+"))
                account_override = last
                tokens = tokens[:-1]
            except ValueError:
                pass

    # 3. Parse amount and payee
    try:
        raw_amount = tokens[-1].replace(",", ".")
        is_income = raw_amount.startswith("+")
        amount = float(raw_amount.lstrip("+"))
        payee = " ".join(tokens[:-1])
        if not payee:
            return None
        return payee, amount, account_override, date_override, is_income
    except ValueError:
        return None
