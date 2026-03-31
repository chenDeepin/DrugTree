"""DrugTree - FastAPI Backend.

Main FastAPI application entry point.
"""

from typing import Any, Optional
import os
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from .models.drug import HealthResponse
from .routers.drugs import router as drugs_router
from .routers.diseases import router as diseases_router
from .routers.admin import router as admin_router
from .routers.graph import router as graph_router
from .services.data_snapshot import get_data_snapshot_service
from .services.request_metrics import get_request_metrics_service

# Initialize FastAPI app
app = FastAPI(
    title="DrugTree API",
    description="Backend API for DrugTree - Visual Drug Universe",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:8765",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:8765",
        "https://chendeepin.github.io",  # GitHub Pages
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

snapshot_service = get_data_snapshot_service()
request_metrics = get_request_metrics_service()


def _root_payload() -> dict[str, Any]:
    return {
        "name": "DrugTree API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "drugs": "/api/v1/drugs",
            "diseases": "/api/v1/diseases",
            "health": "/health",
            "search": "/api/v1/drugs/search",
        },
    }


def _resolve_frontend_url(request: Request) -> Optional[str]:
    configured_url = os.getenv("DRUGTREE_FRONTEND_URL")
    if configured_url:
        return configured_url.rstrip("/") + "/"

    if request.url.hostname in {"127.0.0.1", "localhost"}:
        return f"{request.url.scheme}://{request.url.hostname}:8080/"

    return None


def _root_html(frontend_url: Optional[str]) -> str:
    launch_hint = (
        f'<p><a class="primary-link" href="{frontend_url}">Open the DrugTree frontend</a></p>'
        if frontend_url
        else "<p>Start the frontend static server, then open it in your browser.</p>"
    )

    return f"""
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>DrugTree API</title>
        <style>
          :root {{
            color-scheme: dark;
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          }}
          body {{
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            background: radial-gradient(circle at top, rgba(82, 129, 255, 0.22), transparent 32%), #0b1020;
            color: #e5eefc;
          }}
          main {{
            width: min(760px, calc(100vw - 32px));
            padding: 32px;
            border-radius: 24px;
            background: rgba(10, 16, 32, 0.92);
            border: 1px solid rgba(148, 163, 184, 0.18);
            box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
          }}
          h1 {{
            margin-top: 0;
            font-size: clamp(2rem, 4vw, 3rem);
          }}
          p, li {{
            color: #c2d2ee;
            line-height: 1.6;
          }}
          code {{
            display: block;
            padding: 14px 16px;
            border-radius: 14px;
            background: rgba(15, 23, 42, 0.95);
            border: 1px solid rgba(148, 163, 184, 0.16);
            color: #f8fafc;
            white-space: pre-wrap;
          }}
          .primary-link {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 12px 18px;
            border-radius: 999px;
            background: linear-gradient(135deg, #5b8cff, #27c6d9);
            color: #08111f;
            font-weight: 700;
            text-decoration: none;
          }}
          .secondary-links {{
            display: flex;
            flex-wrap: wrap;
            gap: 14px;
            margin-top: 18px;
          }}
          .secondary-links a {{
            color: #9ed4ff;
          }}
        </style>
      </head>
      <body>
        <main>
          <p>🌳 DrugTree backend</p>
          <h1>This address serves the API, not the atlas UI.</h1>
          <p>
            If you opened the backend in your browser and expected the body atlas or drug cards,
            start the static frontend and open that URL instead.
          </p>
          {launch_hint}
          <code>cd src/frontend
python3 -m http.server 8080</code>
          <div class="secondary-links">
            <a href="/docs">API docs</a>
            <a href="/health">Health check</a>
            <a href="/api/v1/drugs?limit=5">Sample drugs endpoint</a>
          </div>
        </main>
      </body>
    </html>
    """


@app.middleware("http")
async def record_request_timing(request: Request, call_next):
    started = perf_counter()
    response = await call_next(request)
    elapsed_ms = (perf_counter() - started) * 1000
    route_key = request.url.path
    request_metrics.record(route_key, elapsed_ms)
    response.headers["X-DrugTree-Request-Ms"] = f"{elapsed_ms:.3f}"
    return response


# Include routers
app.include_router(drugs_router)
app.include_router(diseases_router)
app.include_router(admin_router)
app.include_router(graph_router)


# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    snapshot = snapshot_service.get_snapshot()
    return HealthResponse(status="ok", version="1.0.0", drugs_count=len(snapshot.drugs))


# Root endpoint
@app.get("/")
async def root(request: Request):
    accept = request.headers.get("accept", "").lower()
    if "text/html" in accept or "application/xhtml+xml" in accept:
        return HTMLResponse(_root_html(_resolve_frontend_url(request)))

    return JSONResponse(_root_payload())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
