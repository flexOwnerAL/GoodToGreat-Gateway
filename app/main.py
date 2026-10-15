import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.openai import router as openai_router
from app.core.config import get_settings
from app.core.logging import setup_logging

setup_logging()
settings = get_settings()
logger = logging.getLogger("goodtogreat")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("%s starting", settings.app_name)
    logger.info(
        "Deepseek-API upstream: %s",
        settings.deepseek_api_base_url,
    )
    yield
    logger.info("%s stopped", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description="Async gateway for pluggable AI providers.",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(openai_router)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": "0.2.0",
        "status": "running",
        "author": "@flexOwnerAL",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway"}
