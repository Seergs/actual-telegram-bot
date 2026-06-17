import httpx
from config import ACTUAL_SERVER_URL, ACTUAL_API_KEY, ACTUAL_BUDGET_ID
from datetime import date

BASE = f"{ACTUAL_SERVER_URL}/v1"
HEADERS = {"x-api-key": ACTUAL_API_KEY, "Content-Type": "application/json"}

TIMEOUT = httpx.Timeout(30.0)

async def fetch_payees() -> list[dict]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(f"{BASE}/budgets/{ACTUAL_BUDGET_ID}/payees", headers=HEADERS)
        r.raise_for_status()
        return r.json()["data"]

async def fetch_accounts() -> list[dict]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(f"{BASE}/budgets/{ACTUAL_BUDGET_ID}/accounts", headers=HEADERS)
        r.raise_for_status()
        return [a for a in r.json()["data"] if not a["closed"] and not a["offbudget"]]

async def insert_transaction(
    payee_name: str,
    amount: float,
    account_id: str,
    tx_date: str | None = None,
    is_income: bool = False
) -> str:
    milliunits = int(round(amount * 100)) if is_income else -int(round(amount * 100))
    payload = {
        "transactions": [{
            "date": tx_date or date.today().isoformat(),
            "amount": milliunits,
            "payee_name": payee_name,
            "cleared": False,
        }]
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            f"{BASE}/budgets/{ACTUAL_BUDGET_ID}/accounts/{account_id}/transactions/import",
            headers=HEADERS,
            json=payload
        )
        r.raise_for_status()
        data = r.json()["data"]
        return data["added"][0] if data["added"] else None

async def delete_transaction(transaction_id: str) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{BASE}/budgets/{ACTUAL_BUDGET_ID}/transactions/{transaction_id}",
            headers=HEADERS
        )
        return r.status_code in (200, 204)
