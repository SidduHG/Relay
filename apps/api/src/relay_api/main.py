from fastapi import FastAPI

from relay_api.api.router import router
from relay_api.lifecycle import lifespan
from relay_api.logging import setup_logging
from relay_api.middleware.error_handler import register_error_handlers

setup_logging()

app = FastAPI(title="RELAY API", lifespan=lifespan)
register_error_handlers(app)
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
