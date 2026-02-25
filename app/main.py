"""
Main FastAPI application for Teiken Claw.

This module provides the FastAPI application with:
- Startup/shutdown lifecycle hooks
- Database initialization
- Health check endpoints
- API routes
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.config.logging import setup_logging, get_logger, set_component, clear_context
from app.config.constants import (
    EVENT_APP_STARTUP,
    EVENT_APP_SHUTDOWN,
    DATA_DIR,
    LOGS_DIR,
    WORKSPACE_DIR,
)
from app.db import init_db, verify_db, dispose_engine


# Configure logging before app creation
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan context manager.
    
    Handles startup and shutdown events:
    - Startup: Initialize database, create directories, apply PRAGMAs
    - Shutdown: Dispose database engine, cleanup resources
    """
    # Startup
    set_component("lifespan")
    logger.info(
        f"Starting {settings.APP_NAME} v{settings.APP_VERSION}",
        extra={"event": EVENT_APP_STARTUP}
    )
    
    try:
        # Create required directories
        _create_directories()
        
        # Initialize database
        logger.info("Initializing database...")
        init_result = await init_db()
        logger.info(
            f"Database initialized: {init_result['status']}",
            extra={
                "event": "database_initialized",
                "pragmas": init_result.get("pragmas", {}),
            }
        )
        
        # Verify database
        verify_result = await verify_db()
        if verify_result["status"] != "healthy":
            logger.warning(
                f"Database verification issues: {verify_result['issues']}",
                extra={"event": "database_verification_warning"}
            )
        else:
            logger.info(
                "Database verification passed",
                extra={"event": "database_verified"}
            )
        
        logger.info(
            f"{settings.APP_NAME} startup complete",
            extra={"event": "startup_complete"}
        )
        
    except Exception as e:
        logger.error(
            f"Startup failed: {e}",
            extra={"event": "startup_error"},
            exc_info=True
        )
        raise
    
    # Yield control to the application
    yield
    
    # Shutdown
    logger.info(
        f"Shutting down {settings.APP_NAME}",
        extra={"event": EVENT_APP_SHUTDOWN}
    )
    
    try:
        # Dispose database engine
        await dispose_engine()
        logger.info(
            "Database engine disposed",
            extra={"event": "database_disposed"}
        )
    except Exception as e:
        logger.error(
            f"Error during shutdown: {e}",
            extra={"event": "shutdown_error"},
            exc_info=True
        )
    
    clear_context()
    logger.info("Shutdown complete")


def _create_directories() -> None:
    """Create required application directories."""
    directories = [
        Path(DATA_DIR),
        Path(LOGS_DIR),
        Path(WORKSPACE_DIR),
        Path(DATA_DIR) / "activity_logs",
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured directory exists: {directory}")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Health Check Endpoints
# =============================================================================

@app.get("/", tags=["root"])
async def root() -> dict:
    """Root endpoint returning basic app info."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """
    Basic health check endpoint.
    
    Returns:
        dict: Health status and version info.
    """
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health/ready", tags=["health"])
async def readiness_check() -> dict:
    """
    Readiness check endpoint.
    
    Verifies database connectivity and returns detailed status.
    
    Returns:
        dict: Readiness status with component details.
    """
    components = {}
    overall_status = "healthy"
    
    # Check database
    try:
        db_result = await verify_db()
        components["database"] = {
            "status": db_result["status"],
            "issues": db_result.get("issues", []),
        }
        if db_result["status"] != "healthy":
            overall_status = "degraded"
    except Exception as e:
        components["database"] = {
            "status": "error",
            "error": str(e),
        }
        overall_status = "unhealthy"
    
    return {
        "status": overall_status,
        "version": settings.APP_VERSION,
        "components": components,
    }


@app.get("/health/live", tags=["health"])
async def liveness_check() -> dict:
    """
    Liveness check endpoint.
    
    Simple check to verify the application is running.
    
    Returns:
        dict: Liveness status.
    """
    return {"status": "alive"}


# =============================================================================
# API Routes
# =============================================================================

@app.get("/api/v1/status", tags=["api"])
async def get_status() -> dict:
    """
    Get application status.
    
    Returns:
        dict: Detailed application status.
    """
    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "debug": settings.DEBUG,
        "features": {
            "cli_enabled": settings.ENABLE_CLI,
            "telegram_enabled": settings.ENABLE_TELEGRAM,
            "memory_enabled": settings.AUTO_MEMORY_ENABLED,
        },
    }


# =============================================================================
# Error Handlers
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors."""
    logger.error(
        f"Unhandled exception: {exc}",
        extra={
            "event": "unhandled_exception",
            "path": str(request.url),
            "method": request.method,
        },
        exc_info=True
    )
    return {
        "error": "Internal server error",
        "detail": str(exc) if settings.DEBUG else "An unexpected error occurred",
    }


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development(),
        log_level=settings.LOG_LEVEL.lower(),
    )
