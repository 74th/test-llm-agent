"""Run the PoC backend with ``uv run python main.py``."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("poc.app:app", host="0.0.0.0", port=8000, reload=True)
