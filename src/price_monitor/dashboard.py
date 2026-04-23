from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

from price_monitor.storage import Storage

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

app = FastAPI(title="Price Monitor")

_storage: Storage | None = None


def set_storage(storage: Storage) -> None:
    global _storage
    _storage = storage


def _get_storage() -> Storage:
    if _storage is None:
        raise RuntimeError("Storage not initialised — call set_storage() before serving requests")
    return _storage


@app.get("/")
async def index(request: Request) -> Any:
    storage = _get_storage()
    products = storage.list_products()
    recent_drops = storage.recent_notifications(limit=10)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "products": products,
            "recent_drops": recent_drops,
        },
    )


@app.get("/api/history/{product_id}")
async def history(product_id: int, days: int = 30) -> JSONResponse:
    storage = _get_storage()
    rows = storage.get_history(product_id, days=days)
    if not rows and product_id not in {p.id for p in storage.list_products()}:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    return JSONResponse(content=rows)
