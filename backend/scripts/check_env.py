import os
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("NEBIUS_API_KEY", "")
enabled = os.getenv("NEBIUS_ENABLED", "False")
print("NEBIUS_API_KEY exists:", bool(key))
print("NEBIUS_ENABLED:", enabled)
