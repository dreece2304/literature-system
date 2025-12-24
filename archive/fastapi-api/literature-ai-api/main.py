"""
Main FastAPI application for literature-ai service.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config.settings import settings
from src.api.endpoints import writer, context, search, system, triager, reader


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events:
    - Initialize logging
    - Load models
    - Connect to services
    - Clean up resources on shutdown
    """
    # Startup
    logger.info("Starting literature-ai service")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Ollama host: {settings.ollama.host}")
    logger.info(f"ChromaDB path: {settings.chromadb.persist_directory}")

    # Import services to trigger initialization
    from src.services.llm_service import get_llm_service
    from src.services.search_service import get_search_service
    from src.context.detector import get_context_detector
    from src.utils.gpu_manager import get_gpu_manager

    try:
        # Test Ollama connection
        llm_service = get_llm_service()
        health = await llm_service.health_check()
        logger.info(f"Ollama health check: {health.get('status', 'unknown')}")

        # Initialize search service (loads vectorstore and embedding model)
        search_service = get_search_service()
        logger.info(f"Search service initialized: {search_service.get_stats()}")

        # Initialize context detector
        get_context_detector()  # Trigger initialization
        logger.info("Context detector initialized")

        # Initialize GPU manager
        gpu_manager = get_gpu_manager()
        device_info = gpu_manager.get_device_info()
        if device_info.get("available"):
            logger.info(f"GPU detected: {device_info.get('name', 'Unknown')}")
            gpu_stats = gpu_manager.get_stats()
            if gpu_stats:
                logger.info(f"VRAM available: {gpu_stats.free_memory_gb:.2f}GB / {gpu_stats.total_memory_gb:.2f}GB")
        else:
            logger.info("No GPU detected, running on CPU")

        logger.info("All services initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        logger.warning("Service starting in degraded mode")

    yield

    # Shutdown
    logger.info("Shutting down literature-ai service")

    # Clean up resources
    try:
        # Unload any loaded models
        llm_service = get_llm_service()
        if llm_service.current_model:
            logger.info(f"Unloading model: {llm_service.current_model}")
            await llm_service._unload_model(llm_service.current_model)

        logger.info("Cleanup completed")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")


# Initialize FastAPI app
app = FastAPI(
    title=settings.api.title,
    description=settings.api.description,
    version=settings.api.version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_origins,
    allow_credentials=settings.api.cors_credentials,
    allow_methods=settings.api.cors_methods,
    allow_headers=settings.api.cors_headers,
)

# Include routers
app.include_router(
    writer.router,
    prefix="/api/v1",
)

app.include_router(
    context.router,
    prefix="/api/v1",
)

app.include_router(
    search.router,
    prefix="/api/v1",
)

app.include_router(
    triager.router,
    prefix="/api/v1",
)

app.include_router(
    reader.router,
    prefix="/api/v1",
)

app.include_router(
    system.router,
    prefix="/api/v1",
)


@app.get("/")
async def root():
    """
    Root endpoint.

    Returns basic service information and directs to documentation.
    """
    return {
        "service": "literature-ai",
        "version": settings.api.version,
        "status": "operational",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


if __name__ == "__main__":
    import uvicorn

    # Run server (logging already configured via src.utils.logging module import)
    uvicorn.run(
        "src.api.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.environment == "development",
        log_level=settings.logging.level.lower(),
    )
