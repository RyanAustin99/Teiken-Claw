"""
Main FastAPI application for Teiken Claw.

This module provides the FastAPI application with:
- Startup/shutdown lifecycle hooks
- Database initialization
- Health check endpoints
- API routes
- Queue system lifecycle management
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

# Agent imports
from app.agent import (
    get_ollama_client,
    get_ollama_circuit_breaker,
    get_circuit_breaker_metrics,
    get_all_circuit_breaker_status,
    get_agent_runtime,
    set_agent_runtime,
    AgentRuntime,
)

# Tool system imports
from app.tools import (
    get_tool_registry,
    set_tool_registry,
    ToolRegistry,
    register_mock_tools,
)

# Queue system imports
from app.queue.dispatcher import JobDispatcher, set_dispatcher
from app.queue.workers import WorkerPool, set_worker_pool
from app.queue.locks import LockManager, set_lock_manager
from app.queue.throttles import RateLimiter, OutboundQueue, set_rate_limiter, set_outbound_queue
from app.queue.dead_letter import DeadLetterQueue, set_dead_letter_queue

# Interface imports
from app.interfaces import (
    TelegramBot,
    TelegramSender,
    CommandRouter,
    HAS_TELEGRAM,
    set_telegram_bot,
    set_telegram_sender,
)

# Memory system imports
from app.memory.store import MemoryStore, get_memory_store, set_memory_store
from app.memory.thread_state import ThreadState, get_thread_state, set_thread_state
from app.memory.extraction_rules import MemoryExtractionRules, get_extraction_rules, set_extraction_rules
from app.agent.context_router import ContextRouter, get_context_router, set_context_router

# Phase 7: Memory embeddings and retrieval imports
from app.memory.embeddings import EmbeddingService, get_embedding_service, set_embedding_service
from app.memory.retrieval import MemoryRetriever, get_retriever, set_retriever
from app.memory.dedupe import MemoryDeduplicator, get_deduplicator, set_deduplicator
from app.memory.extractor_llm import LLMMemoryExtractor, get_llm_extractor, set_llm_extractor


# Configure logging before app creation
setup_logging()
logger = get_logger(__name__)


# Global queue components
_dispatcher: JobDispatcher = None
_lock_manager: LockManager = None
_dead_letter_queue: DeadLetterQueue = None
_worker_pool: WorkerPool = None
_rate_limiter: RateLimiter = None
_outbound_queue: OutboundQueue = None

# Global agent components
_tool_registry: ToolRegistry = None
_agent_runtime: AgentRuntime = None

# Global interface components
_telegram_bot: TelegramBot = None
_telegram_sender: TelegramSender = None
_command_router: CommandRouter = None

# Global memory components
_memory_store: MemoryStore = None
_thread_state: ThreadState = None
_extraction_rules: MemoryExtractionRules = None
_context_router: ContextRouter = None

# Phase 7: Global embedding and retrieval components
_embedding_service: EmbeddingService = None
_memory_retriever: MemoryRetriever = None
_memory_deduplicator: MemoryDeduplicator = None
_llm_extractor: LLMMemoryExtractor = None


async def _initialize_queue_system() -> dict:
    """
    Initialize the queue system components.
    
    Creates and connects:
    - DeadLetterQueue
    - LockManager
    - JobDispatcher
    - RateLimiter
    - OutboundQueue
    - ToolRegistry
    - AgentRuntime
    - MemoryStore
    - ThreadState
    - MemoryExtractionRules
    - ContextRouter
    - WorkerPool
    - TelegramSender
    - TelegramBot (if enabled)
    
    Returns:
        dict: Initialization status for each component
    """
    global _dispatcher, _lock_manager, _dead_letter_queue, _worker_pool, _rate_limiter, _outbound_queue
    global _tool_registry, _agent_runtime
    global _telegram_bot, _telegram_sender, _command_router
    global _memory_store, _thread_state, _extraction_rules, _context_router
    global _embedding_service, _memory_retriever, _memory_deduplicator, _llm_extractor
    
    status = {}
    
    try:
        # 1. Initialize Dead-Letter Queue
        logger.info("Initializing dead-letter queue...")
        _dead_letter_queue = DeadLetterQueue()
        set_dead_letter_queue(_dead_letter_queue)
        status["dead_letter_queue"] = "initialized"
        
        # 2. Initialize Lock Manager
        logger.info("Initializing lock manager...")
        _lock_manager = LockManager(default_timeout=settings.LOCK_TIMEOUT_SEC)
        set_lock_manager(_lock_manager)
        status["lock_manager"] = "initialized"
        
        # 3. Initialize Job Dispatcher
        logger.info("Initializing job dispatcher...")
        _dispatcher = JobDispatcher(
            max_size=settings.QUEUE_MAX_SIZE,
            idempotency_ttl_seconds=settings.IDEMPOTENCY_TTL_SEC,
            dead_letter_queue=_dead_letter_queue,
        )
        set_dispatcher(_dispatcher)
        status["dispatcher"] = "initialized"
        
        # Connect dispatcher to dead-letter queue for replay
        _dead_letter_queue.set_dispatcher(_dispatcher)
        
        # 4. Initialize Rate Limiter
        logger.info("Initializing rate limiter...")
        _rate_limiter = RateLimiter(
            global_rate=settings.TELEGRAM_GLOBAL_MSG_PER_SEC,
            per_chat_rate=settings.TELEGRAM_PER_CHAT_MSG_PER_SEC,
        )
        set_rate_limiter(_rate_limiter)
        status["rate_limiter"] = "initialized"
        
        # 5. Initialize Outbound Queue
        logger.info("Initializing outbound queue...")
        _outbound_queue = OutboundQueue(
            rate_limiter=_rate_limiter,
            global_rate=settings.TELEGRAM_GLOBAL_MSG_PER_SEC,
            per_chat_rate=settings.TELEGRAM_PER_CHAT_MSG_PER_SEC,
            max_queue_size=settings.QUEUE_MAX_SIZE,
            max_attempts=settings.JOB_MAX_ATTEMPTS,
            dead_letter_queue=_dead_letter_queue,
        )
        set_outbound_queue(_outbound_queue)
        status["outbound_queue"] = "initialized"
        
        # 6. Initialize Tool Registry
        logger.info("Initializing tool registry...")
        _tool_registry = ToolRegistry()
        set_tool_registry(_tool_registry)
        
        # Register mock tools for development
        if settings.is_development():
            logger.info("Registering mock tools for development...")
            register_mock_tools(_tool_registry)
        
        status["tool_registry"] = "initialized"
        status["tool_count"] = len(_tool_registry)
        
        # 7. Initialize Agent Runtime
        logger.info("Initializing agent runtime...")
        _agent_runtime = AgentRuntime(tool_registry=_tool_registry)
        set_agent_runtime(_agent_runtime)
        status["agent_runtime"] = "initialized"
        
        # 8. Initialize Memory Store
        logger.info("Initializing memory store...")
        _memory_store = get_memory_store()
        set_memory_store(_memory_store)
        status["memory_store"] = "initialized"
        
        # 9. Initialize Thread State
        logger.info("Initializing thread state...")
        _thread_state = get_thread_state()
        set_thread_state(_thread_state)
        status["thread_state"] = "initialized"
        
        # 10. Initialize Extraction Rules
        logger.info("Initializing extraction rules...")
        _extraction_rules = get_extraction_rules()
        set_extraction_rules(_extraction_rules)
        status["extraction_rules"] = "initialized"
        
        # 11. Initialize Context Router
        logger.info("Initializing context router...")
        _context_router = get_context_router()
        set_context_router(_context_router)
        status["context_router"] = "initialized"
        
        # 12. Initialize Embedding Service (Phase 7)
        logger.info("Initializing embedding service...")
        _embedding_service = get_embedding_service()
        set_embedding_service(_embedding_service)
        status["embedding_service"] = "initialized"
        
        # 13. Initialize Memory Retriever (Phase 7)
        logger.info("Initializing memory retriever...")
        _memory_retriever = get_retriever()
        set_retriever(_memory_retriever)
        status["memory_retriever"] = "initialized"
        
        # 14. Initialize Memory Deduplicator (Phase 7)
        logger.info("Initializing memory deduplicator...")
        _memory_deduplicator = get_deduplicator()
        set_deduplicator(_memory_deduplicator)
        status["memory_deduplicator"] = "initialized"
        
        # 15. Initialize LLM Memory Extractor (Phase 7)
        logger.info("Initializing LLM memory extractor...")
        _llm_extractor = get_llm_extractor()
        set_llm_extractor(_llm_extractor)
        status["llm_extractor"] = "initialized"
        
        # 16. Initialize Worker Pool
        logger.info("Initializing worker pool...")
        _worker_pool = WorkerPool(
            dispatcher=_dispatcher,
            lock_manager=_lock_manager,
            num_workers=settings.WORKER_COUNT,
            ollama_concurrency=settings.OLLAMA_MAX_CONCURRENCY,
            lock_timeout=settings.LOCK_TIMEOUT_SEC,
        )
        set_worker_pool(_worker_pool)
        status["worker_pool"] = "initialized"
        
        # 13. Initialize Command Router
        logger.info("Initializing command router...")
        _command_router = CommandRouter()
        status["command_router"] = "initialized"
        
        # 14. Initialize Telegram Sender
        logger.info("Initializing Telegram sender...")
        _telegram_sender = TelegramSender(
            token=settings.TELEGRAM_BOT_TOKEN,
            outbound_queue=_outbound_queue,
        )
        set_telegram_sender(_telegram_sender)
        status["telegram_sender"] = "initialized"
        
        # 15. Initialize Telegram Bot (if enabled)
        if settings.ENABLE_TELEGRAM and HAS_TELEGRAM and settings.TELEGRAM_BOT_TOKEN:
            logger.info("Initializing Telegram bot...")
            _telegram_bot = TelegramBot(
                token=settings.TELEGRAM_BOT_TOKEN,
                command_router=_command_router,
            )
            set_telegram_bot(_telegram_bot)
            status["telegram_bot"] = "initialized"
        elif settings.ENABLE_TELEGRAM and not HAS_TELEGRAM:
            logger.warning(
                "Telegram enabled but python-telegram-bot not installed",
                extra={"event": "telegram_not_available"}
            )
            status["telegram_bot"] = "disabled_no_library"
        elif settings.ENABLE_TELEGRAM and not settings.TELEGRAM_BOT_TOKEN:
            logger.warning(
                "Telegram enabled but no bot token configured",
                extra={"event": "telegram_no_token"}
            )
            status["telegram_bot"] = "disabled_no_token"
        else:
            status["telegram_bot"] = "disabled"
        
        logger.info(
            "Queue system initialized",
            extra={"event": "queue_system_initialized", "status": status}
        )
        
    except Exception as e:
        logger.error(
            f"Failed to initialize queue system: {e}",
            extra={"event": "queue_system_init_error"},
            exc_info=True,
        )
        raise
    
    return status


async def _start_queue_workers() -> dict:
    """
    Start the queue workers and outbound sender.
    
    Returns:
        dict: Status of each started component
    """
    status = {}
    
    try:
        # Start worker pool
        if _worker_pool:
            logger.info(f"Starting worker pool with {settings.WORKER_COUNT} workers...")
            await _worker_pool.start()
            status["worker_pool"] = "started"
        
        # Start outbound sender
        if _outbound_queue:
            logger.info("Starting outbound queue sender...")
            await _outbound_queue.start_sender()
            status["outbound_queue"] = "started"
        
        # Start Telegram sender loop
        if _telegram_sender:
            logger.info("Starting Telegram sender loop...")
            await _telegram_sender.start_sender_loop()
            status["telegram_sender"] = "started"
        
        # Start Telegram bot (if enabled and initialized)
        if _telegram_bot and settings.ENABLE_TELEGRAM:
            logger.info("Starting Telegram bot...")
            await _telegram_bot.start()
            status["telegram_bot"] = "started"
        
        logger.info(
            "Queue workers started",
            extra={"event": "queue_workers_started", "status": status}
        )
        
    except Exception as e:
        logger.error(
            f"Failed to start queue workers: {e}",
            extra={"event": "queue_workers_start_error"},
            exc_info=True,
        )
        raise
    
    return status


async def _stop_queue_workers() -> dict:
    """
    Stop the queue workers and outbound sender gracefully.
    
    Returns:
        dict: Status of each stopped component
    """
    status = {}
    
    # Stop Telegram bot first
    if _telegram_bot:
        try:
            logger.info("Stopping Telegram bot...")
            await _telegram_bot.stop()
            status["telegram_bot"] = "stopped"
        except Exception as e:
            logger.error(f"Error stopping Telegram bot: {e}", exc_info=True)
            status["telegram_bot"] = f"error: {e}"
    
    # Stop Telegram sender
    if _telegram_sender:
        try:
            logger.info("Stopping Telegram sender...")
            await _telegram_sender.stop_sender(timeout=30.0)
            status["telegram_sender"] = "stopped"
        except Exception as e:
            logger.error(f"Error stopping Telegram sender: {e}", exc_info=True)
            status["telegram_sender"] = f"error: {e}"
    
    # Stop worker pool
    if _worker_pool:
        try:
            logger.info("Stopping worker pool...")
            await _worker_pool.stop(timeout=30.0)
            status["worker_pool"] = "stopped"
        except Exception as e:
            logger.error(f"Error stopping worker pool: {e}", exc_info=True)
            status["worker_pool"] = f"error: {e}"
    
    # Stop outbound sender
    if _outbound_queue:
        try:
            logger.info("Stopping outbound queue sender...")
            await _outbound_queue.stop_sender(timeout=30.0)
            status["outbound_queue"] = "stopped"
        except Exception as e:
            logger.error(f"Error stopping outbound queue: {e}", exc_info=True)
            status["outbound_queue"] = f"error: {e}"
    
    # Shutdown dispatcher
    if _dispatcher:
        try:
            logger.info("Shutting down dispatcher...")
            await _dispatcher.shutdown(wait=True)
            status["dispatcher"] = "shutdown"
        except Exception as e:
            logger.error(f"Error shutting down dispatcher: {e}", exc_info=True)
            status["dispatcher"] = f"error: {e}"
    
    logger.info(
        "Queue workers stopped",
        extra={"event": "queue_workers_stopped", "status": status}
    )
    
    return status


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan context manager.
    
    Handles startup and shutdown events:
    - Startup: Initialize database, create directories, apply PRAGMAs, start queue system
    - Shutdown: Stop queue workers, dispose database engine, cleanup resources
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
        
        # Initialize queue system
        logger.info("Initializing queue system...")
        queue_status = await _initialize_queue_system()
        logger.info(
            f"Queue system initialized: {queue_status}",
            extra={"event": "queue_system_ready"}
        )
        
        # Start queue workers
        logger.info("Starting queue workers...")
        workers_status = await _start_queue_workers()
        logger.info(
            f"Queue workers started: {workers_status}",
            extra={"event": "queue_workers_ready"}
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
    
    # Stop queue workers
    try:
        await _stop_queue_workers()
    except Exception as e:
        logger.error(
            f"Error stopping queue workers: {e}",
            extra={"event": "queue_shutdown_error"},
            exc_info=True
        )
    
    # Dispose database engine
    try:
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
    # Get circuit breaker metrics
    cb_metrics = get_circuit_breaker_metrics()
    
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "circuit_breakers": {
            "total": cb_metrics.total_breakers,
            "healthy": cb_metrics.closed_count,
            "open": cb_metrics.open_count,
            "half_open": cb_metrics.half_open_count,
        },
    }


@app.get("/health/ready", tags=["health"])
async def readiness_check() -> dict:
    """
    Readiness check endpoint.
    
    Verifies database connectivity, queue system status, and Ollama connectivity.
    
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
    
    # Check Ollama connectivity
    try:
        ollama_client = get_ollama_client()
        ollama_health = await ollama_client.check_health()
        components["ollama"] = {
            "status": ollama_health["status"],
            "base_url": ollama_health.get("base_url"),
            "model_count": ollama_health.get("model_count", 0),
            "circuit_breaker": ollama_health.get("circuit_breaker", {}).get("state", "unknown"),
        }
        if ollama_health["status"] != "healthy":
            overall_status = "degraded"
    except Exception as e:
        components["ollama"] = {
            "status": "error",
            "error": str(e),
        }
        overall_status = "degraded"  # Ollama not critical for basic readiness
    
    # Check queue system
    if _dispatcher:
        components["queue"] = {
            "status": "healthy" if not _dispatcher.is_shutdown else "shutdown",
            "queue_depth": _dispatcher.queue_depth,
            "pending_count": _dispatcher.pending_count,
        }
    else:
        components["queue"] = {"status": "not_initialized"}
        overall_status = "degraded"
    
    # Check worker pool
    if _worker_pool:
        worker_status = _worker_pool.get_status()
        components["workers"] = {
            "status": "healthy" if worker_status["running"] else "stopped",
            "active_workers": worker_status["active_workers"],
            "total_jobs_processed": worker_status["total_jobs_processed"],
        }
    else:
        components["workers"] = {"status": "not_initialized"}
    
    # Check outbound queue
    if _outbound_queue:
        components["outbound"] = {
            "status": "healthy" if _outbound_queue.is_running else "stopped",
            "queue_depth": _outbound_queue.queue_depth,
        }
    else:
        components["outbound"] = {"status": "not_initialized"}
    
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


@app.get("/api/v1/queue/status", tags=["api"])
async def get_queue_status() -> dict:
    """
    Get queue system status.
    
    Returns:
        dict: Detailed queue system status.
    """
    status = {
        "dispatcher": _dispatcher.get_stats() if _dispatcher else None,
        "workers": _worker_pool.get_status() if _worker_pool else None,
        "outbound": _outbound_queue.get_stats() if _outbound_queue else None,
        "locks": _lock_manager.get_lock_count() if _lock_manager else None,
        "dead_letter": _dead_letter_queue.get_stats() if _dead_letter_queue else None,
    }
    
    return status


@app.get("/api/v1/queue/dead-letter", tags=["api"])
async def list_dead_letter(limit: int = 50, offset: int = 0) -> dict:
    """
    List dead-letter queue entries.
    
    Args:
        limit: Maximum number of entries to return
        offset: Number of entries to skip
    
    Returns:
        dict: List of dead-letter entries
    """
    if not _dead_letter_queue:
        return {"error": "Dead-letter queue not initialized", "entries": []}
    
    entries = await _dead_letter_queue.list(limit=limit, offset=offset)
    count = await _dead_letter_queue.count()
    
    return {
        "entries": entries,
        "total": count,
        "limit": limit,
        "offset": offset,
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
