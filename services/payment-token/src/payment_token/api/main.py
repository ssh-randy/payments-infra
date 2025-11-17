"""FastAPI application for Payment Token Service.

This module sets up the FastAPI application with all routes and middleware.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from payment_token.api.routes import router as public_router
from payment_token.api.internal_routes import router as internal_router
from payment_token.config import settings

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="Payment Token Service",
    description="PCI-compliant payment tokenization service",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,  # Disable docs in production
    redoc_url="/redoc" if settings.debug else None,
)

# Configure CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002"],  # Frontend dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(public_router)  # Public API routes (POST /v1/payment-tokens, GET /v1/payment-tokens/{id})
app.include_router(internal_router)  # Internal API routes (POST /internal/v1/decrypt)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "payment-token"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "payment-token",
        "version": "0.1.0",
        "environment": settings.environment,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "payment_token.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )
