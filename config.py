import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_ALLOWED_USER_ID = int(os.environ["TELEGRAM_ALLOWED_USER_ID"])
ACTUAL_SERVER_URL = os.environ["ACTUAL_SERVER_URL"]
ACTUAL_API_KEY = os.environ["ACTUAL_API_KEY"]
ACTUAL_BUDGET_ID = os.environ["ACTUAL_BUDGET_ID"]
ACTUAL_ACCOUNT_DEFAULT = os.environ.get("ACTUAL_ACCOUNT_DEFAULT", "")
