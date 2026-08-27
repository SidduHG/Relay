from fastapi import FastAPI

from relay_api.lifecycle import lifespan
from relay_api.logging import setup_logging

setup_logging()

app = FastAPI(title="RELAY API", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
