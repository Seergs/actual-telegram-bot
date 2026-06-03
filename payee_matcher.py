from rapidfuzz import process, fuzz

SCORE_AUTO = 85
SCORE_SUGGEST = 60

def match_payee(query: str, payees: list[dict]) -> dict:
    names = [p["name"] for p in payees if not p.get("transfer_acct")]
    result = process.extractOne(query, names, scorer=fuzz.WRatio)

    if not result:
        return {"type": "none"}

    name, score, _ = result

    if score >= SCORE_AUTO:
        return {"type": "auto", "payee": name, "score": score}
    elif score >= SCORE_SUGGEST:
        suggestions = process.extract(query, names, scorer=fuzz.WRatio, limit=3)
        return {
            "type": "suggest",
            "options": [s[0] for s in suggestions]
        }
    else:
        return {"type": "none", "query": query}

def parse_message(text: str) -> tuple[str, float] | None:
    tokens = text.strip().split()
    if len(tokens) < 2:
        return None
    try:
        amount = float(tokens[-1].replace(",", "."))
        payee = " ".join(tokens[:-1])
        return payee, amount
    except ValueError:
        return None
