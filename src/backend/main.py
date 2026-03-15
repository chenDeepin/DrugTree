"""
DrugTree - FastAPI Backend

Main FastAPI application entry point.
"""

import json
from pathlib import Path
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models.drug import HealthResponse
from routers.drugs import router as drugs_router
from routers.diseases import router as diseases_router

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

# Load drug data
DATA_PATH = Path(__file__).parent.parent.parent / "data" / "drugs.json"


def load_drugs() -> List[dict]:
    """Load drugs from JSON file"""
    try:
        with open(DATA_PATH, "r") as f:
            data = json.load(f)
            return data.get("drugs", [])
    except Exception as e:
        print(f"Error loading drugs: {e}")
        return []


# Store drugs in memory
drugs_db = load_drugs()

# Include routers
app.include_router(drugs_router)
app.include_router(diseases_router)


# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(status="ok", version="1.0.0", drugs_count=len(drugs_db))


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API info"""
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
