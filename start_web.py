"""Hosting entry point; run from the project directory with python start_web.py."""
import os

import uvicorn


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, workers=1)
