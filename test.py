import os
from pathlib import Path

import requests
from dotenv import load_dotenv


ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH, override=True)

token = os.getenv("GH_API_KEY", "").strip()

headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {token}",
    "X-GitHub-Api-Version": "2022-11-28",
}

response = requests.get(
    "https://api.github.com/user",
    headers=headers,
    timeout=30,
)

print("Status:", response.status_code)
print("Response:", response.text)