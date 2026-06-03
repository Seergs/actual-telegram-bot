from rapidfuzz import process, fuzz
import unicodedata

SCORE_AUTO = 85
SCORE_SUGGEST = 60

def normalize(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("utf-8").lower()

def match_payee(query: str, payees: list[dict]) -> dict:
    names = [p["name"] for p in payees if not p.get("transfer_acct")]

    # Exact match case-insensitive
    for name in names:
        if name.lower() == query.lower():
            return {"type": "auto", "payee": name, "score": 100}

    result = process.extractOne(query, names, scorer=fuzz.WRatio)
    print(f"query: {query}, best match: {result}")

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

def parse_message_with_account(text: str, accounts: list[dict]) -> tuple[str, float, str | None] | None:
    tokens = text.strip().split()
    if len(tokens) < 2:
        return None

    account_override = None

    if len(tokens) >= 3:
        last = tokens[-1]
        is_number = last.isdigit()
        is_account = any(
            normalize(last) in normalize(a["name"])
            for a in accounts
        )
        if is_number or is_account:
            try:
                float(tokens[-2].replace(",", "."))
                account_override = last
                tokens = tokens[:-1]
            except ValueError:
                pass

    try:
        amount = float(tokens[-1].replace(",", "."))
        payee = " ".join(tokens[:-1])
        if not payee:
            return None
        return payee, amount, account_override
    except ValueError:
        return None
