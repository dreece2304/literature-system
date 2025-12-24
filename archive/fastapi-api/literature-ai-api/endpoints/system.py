"""
System API endpoints (health, stats, monitoring).
"""

from fastapi import APIRouter, HTTPException, status
from loguru import logger

from config.settings import settings
from src.api.schemas import HealthCheckResponse, StatsResponse
from src.services.llm_service import get_llm_service
from src.services.search_service import get_search_service
from src.context.detector import get_context_detector
from src.utils.gpu_manager import get_gpu_manager

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Health check",
    description="Check service health and component status",
)
async def health_check():
    """
    Perform health check.

    Checks:
    - Ollama service availability
    - Model availability
    - GPU status
    - Vector store
    - Context tracking

    Returns overall health status and component details.
    """
    try:
        llm_service = get_llm_service()

        # Check LLM service
        llm_health = await llm_service.health_check()

        # Check search service
        search_service = get_search_service()
        search_stats = search_service.get_stats()

        # Check context detector
        context_detector = get_context_detector()
        context_stats = context_detector.get_stats()

        # Check GPU
        gpu_manager = get_gpu_manager()
        gpu_stats = gpu_manager.get_stats()

        # Determine overall status
        overall_status = "healthy"
        if llm_health.get("status") != "healthy":
            overall_status = llm_health.get("status", "unknown")

        return HealthCheckResponse(
            status=overall_status,
            service="literature-ai",
            version=settings.api.version,
            components={
                "llm": llm_health,
                "search": {"status": "healthy", **search_stats},
                "context": {"status": "healthy", **context_stats},
                "gpu": gpu_stats,
            },
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}",
        )


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Get system statistics",
    description="Get detailed statistics about all system components",
)
async def get_stats():
    """
    Get system statistics.

    Returns detailed stats for:
    - Embedding generation
    - Vector store
    - Context tracking
    - LLM service

    Useful for monitoring and debugging.
    """
    try:
        # Search/embedding stats
        search_service = get_search_service()

        # Vector store stats
        vectorstore_stats = search_service.vectorstore.get_stats()

        # Context stats
        context_detector = get_context_detector()
        context_stats = context_detector.get_stats()

        # LLM stats
        llm_service = get_llm_service()
        llm_health = await llm_service.health_check()

        return StatsResponse(
            embedding_stats={
                "model": search_service.generator.model_name,
                "dimension": search_service.generator.dimension,
                "device": search_service.generator.device,
            },
            vectorstore_stats=vectorstore_stats,
            context_stats=context_stats,
            llm_stats={
                "current_model": llm_service.current_model,
                "base_url": llm_service.base_url,
                **llm_health,
            },
        )

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}",
        )


@router.get(
    "/",
    summary="API info",
    description="Get API information and available endpoints",
)
async def get_api_info():
    """
    Get API information.

    Returns:
    - Service name and version
    - Available endpoints
    - Configuration
    """
    return {
        "service": "literature-ai",
        "version": settings.api.version,
        "title": settings.api.title,
        "description": settings.api.description,
        "environment": settings.environment,
        "endpoints": {
            "writer": "/api/v1/writer/*",
            "context": "/api/v1/context/*",
            "search": "/api/v1/search/*",
            "health": "/health",
            "stats": "/stats",
            "docs": "/docs",
        },
    }


@router.get(
    "/gpu",
    summary="GPU information",
    description="Get GPU status and memory usage",
)
async def get_gpu_info():
    """
    Get GPU information.

    Returns:
    - GPU device info
    - Memory usage
    - Temperature
    - Loaded models
    """
    try:
        gpu_manager = get_gpu_manager()

        device_info = gpu_manager.get_device_info()
        stats = gpu_manager.get_stats()

        return {
            "device": device_info,
            "stats": stats.to_dict() if stats else None,
            "loaded_models": list(gpu_manager.loaded_models.keys()),
        }

    except Exception as e:
        logger.error(f"Failed to get GPU info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get GPU info: {str(e)}",
        )
