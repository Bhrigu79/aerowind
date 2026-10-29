import asyncio
import os
import sys

# Ensure backend root is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings

def preflight_checks():
    errors = []
    if not settings.NEBIUS_API_KEY:
        errors.append("NEBIUS_API_KEY is missing or empty")
    if not settings.NEBIUS_ENABLED:
        errors.append("NEBIUS_ENABLED is not True")
    if settings.NEBIUS_DEFAULT_MODEL != "nvidia/llama-3.1-nemotron-70b-instruct":
        errors.append(f"Model mismatch, found {settings.NEBIUS_DEFAULT_MODEL}")

    return errors

if __name__ == "__main__":
    errs = preflight_checks()
    if errs:
        print("PREFLIGHT FAILED:")
        for e in errs:
            print("-", e)
    else:
        print("PREFLIGHT PASSED")
