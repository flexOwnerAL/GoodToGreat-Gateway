import hmac
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes.openai import router as openai_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.observability import record_request, snapshot
from app.core.ratelimit import check_rate_limit
from app.providers import init_providers, registry

setup_logging()
settings = get_settings()
logger = logging.getLogger("goodtogreat")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("%s starting", settings.app_name)
    init_providers()
    logger.info("Registered providers: %s", registry.names())
    logger.info("DeepBridge integration configured")
    if settings.gtg_api_key:
        logger.info("GTG API-key authentication enabled")
    else:
        logger.warning("GTG_API_KEY is empty; /v1 endpoints are unauthenticated")
    yield
    logger.info("%s stopped", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description="Async multi-provider AI gateway with DeepBridge, g4f (in-process), and local Ollama support.",
    version="0.5.0",
    lifespan=lifespan,
)


def _client_identity(request: Request) -> str:
    """Rate-limit key: the bearer token when present, else the client IP."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return "key:" + auth[7:].strip()
    client = request.client
    return "ip:" + (client.host if client else "unknown")


@app.middleware("http")
async def security_and_metrics(request: Request, call_next):
    started = time.perf_counter()
    path = request.url.path

    # Body size cap (checked before parsing to bound memory/CPU use).
    if path.startswith("/v1/"):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > settings.max_request_body_bytes:
                    response = JSONResponse(
                        status_code=413,
                        content={"error": {
                            "message": f"Request body exceeds the {settings.max_request_body_bytes}-byte limit.",
                            "type": "invalid_request_error", "param": None, "code": "request_too_large",
                        }},
                    )
                    record_request(request.method, path, response.status_code, time.perf_counter() - started)
                    return response
            except ValueError:
                pass

    # Bearer-token authentication.
    if path.startswith("/v1/") and settings.gtg_api_key:
        supplied = request.headers.get("authorization", "")
        expected = f"Bearer {settings.gtg_api_key}"
        if not hmac.compare_digest(supplied, expected):
            response = JSONResponse(
                status_code=401,
                content={"error": {
                    "message": "Missing or invalid API key.", "type": "authentication_error",
                    "param": None, "code": "invalid_api_key",
                }},
                headers={"WWW-Authenticate": "Bearer"},
            )
            record_request(request.method, path, response.status_code, time.perf_counter() - started)
            return response

    # Token-bucket rate limiting.
    if path.startswith("/v1/"):
        allowed, retry_after = check_rate_limit(_client_identity(request))
        if not allowed:
            response = JSONResponse(
                status_code=429,
                content={"error": {
                    "message": "Rate limit exceeded. Slow down and retry shortly.",
                    "type": "rate_limit_error", "param": None, "code": "rate_limit_exceeded",
                }},
                headers={"Retry-After": str(max(1, int(retry_after + 0.999)))},
            )
            record_request(request.method, path, response.status_code, time.perf_counter() - started)
            return response

    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request error: %s %s", request.method, path)
        response = JSONResponse(
            status_code=500,
            content={"error": {"message": "Internal server error.", "type": "gateway_error"}},
        )
    record_request(request.method, path, response.status_code, time.perf_counter() - started)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


app.include_router(openai_router)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": "0.5.0",
        "status": "running",
        "author": "@flexOwnerAL",
        "providers": ["deepbridge"] + registry.names(),
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway", "version": "0.5.0"}


@app.get("/health/providers")
async def health_providers():
    """Best-effort reachability check for each configured provider.

    DeepBridge is never probed to avoid triggering its login/PoW flow;
    its status is reported as 'configured' only.
    All other providers run their own health_check() method.
    """
    result = {
        "deepbridge": {
            "enabled": True,
            "note": "Not probed — avoids triggering the DeepSeek login/PoW flow.",
        }
    }
    for name in registry.names():
        try:
            provider = registry.get(name)
            result[name] = await provider.health_check()
        except Exception as exc:
            result[name] = {"reachable": False, "error": str(exc)}
    return result


@app.get("/metrics")
async def metrics():
    """Lightweight JSON metrics — never includes prompts, credentials, or cookies."""
    return snapshot()
