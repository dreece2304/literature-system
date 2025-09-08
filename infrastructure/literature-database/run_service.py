#!/usr/bin/env python3
"""
Literature Database Service Startup Script

Starts the FastAPI service for the literature-database service in the research monorepo.

Usage:
    python run_service.py
    
The service will run on port 8001 by default for monorepo compatibility.
"""

import os
import sys
import argparse
from pathlib import Path

# Add src directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn
from loguru import logger

def setup_logging():
    """Configure logging for the service using new configuration system."""
    try:
        from src.config import get_config
        config = get_config()
        
        # Ensure logs directory exists
        logs_dir = Path(config.logging.file).parent
        logs_dir.mkdir(exist_ok=True, parents=True)
        
        # Configure loguru
        logger.remove()  # Remove default handler
        
        # Add console logging
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level=config.logging.level
        )
        
        # Add file logging (without compression to avoid gzip issue)
        logger.add(
            config.logging.file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level=config.logging.level,
            rotation=config.logging.max_size,
            retention=config.logging.backup_count
        )
        
    except Exception as e:
        # Fallback to simple logging if config fails
        logger.remove()
        logger.add(sys.stdout, level="INFO")
        logger.warning(f"Failed to load configuration, using fallback logging: {e}")


def check_environment():
    """Check that the environment is set up correctly."""
    logger.info("Checking environment...")
    
    # Check required directories exist
    required_dirs = ["data", "config", "logs"]
    for dir_name in required_dirs:
        dir_path = Path(dir_name)
        if not dir_path.exists():
            logger.warning(f"Creating missing directory: {dir_name}")
            dir_path.mkdir(parents=True, exist_ok=True)
    
    # Check config file exists
    config_path = Path("config/settings.yml")
    if not config_path.exists():
        logger.error(f"Configuration file not found: {config_path}")
        logger.error("Please ensure config/settings.yml exists before starting the service")
        return False
    
    # Check database is accessible
    try:
        from src.database import get_engine, load_config
        config = load_config()
        engine = get_engine(config)
        
        # Test connection
        with engine.connect() as conn:
            logger.info(f"Database connection successful: {engine.url}")
        
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        logger.error("Please check your database configuration in config/settings.yml")
        return False
    
    logger.info("Environment check passed ✓")
    return True


def main():
    """Main entry point for the service."""
    parser = argparse.ArgumentParser(description="Literature Database Service")
    
    # Load config for defaults
    try:
        from src.config import get_config
        config = get_config()
        default_host = config.service.host
        default_port = config.service.port
        default_reload = config.service.reload
    except Exception:
        default_host = "0.0.0.0"
        default_port = 8001
        default_reload = False
    
    parser.add_argument(
        "--host", 
        default=default_host, 
        help=f"Host to bind to (default: {default_host})"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=default_port, 
        help=f"Port to bind to (default: {default_port})"
    )
    parser.add_argument(
        "--reload", 
        action="store_true",
        default=default_reload,
        help="Enable auto-reload for development"
    )
    parser.add_argument(
        "--workers", 
        type=int, 
        default=1, 
        help="Number of worker processes (default: 1)"
    )
    parser.add_argument(
        "--log-level", 
        choices=["critical", "error", "warning", "info", "debug"], 
        default="info",
        help="Log level (default: info)"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging()
    
    logger.info("=" * 60)
    logger.info("Literature Database Service")
    logger.info("=" * 60)
    logger.info(f"Version: 1.0.0")
    logger.info(f"Host: {args.host}")
    logger.info(f"Port: {args.port}")
    logger.info(f"Workers: {args.workers}")
    logger.info(f"Reload: {args.reload}")
    logger.info(f"Log Level: {args.log_level}")
    logger.info("=" * 60)
    
    # Check environment
    if not check_environment():
        logger.error("Environment check failed. Exiting.")
        sys.exit(1)
    
    logger.info("Starting Literature Database Service...")
    
    # Import the FastAPI app
    try:
        from src.api.main import app
        logger.info("FastAPI application loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load FastAPI application: {e}")
        sys.exit(1)
    
    # Configure uvicorn settings
    uvicorn_config = {
        "app": "src.api.main:app",
        "host": args.host,
        "port": args.port,
        "log_level": args.log_level,
        "access_log": True,
    }
    
    # Add development settings
    if args.reload:
        uvicorn_config["reload"] = True
        uvicorn_config["reload_dirs"] = ["src"]
        logger.info("Auto-reload enabled for development")
    else:
        uvicorn_config["workers"] = args.workers
    
    try:
        # Start the server
        logger.info(f"Service starting on http://{args.host}:{args.port}")
        logger.info(f"API Documentation: http://{args.host}:{args.port}/docs")
        logger.info(f"Health Check: http://{args.host}:{args.port}/health")
        
        uvicorn.run(**uvicorn_config)
        
    except KeyboardInterrupt:
        logger.info("Service shutdown requested by user")
    except Exception as e:
        logger.error(f"Service failed to start: {e}")
        sys.exit(1)
    finally:
        logger.info("Literature Database Service stopped")


if __name__ == "__main__":
    main()