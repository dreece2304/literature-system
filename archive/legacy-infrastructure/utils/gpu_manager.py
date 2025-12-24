"""
GPU memory management and monitoring.

Provides utilities for monitoring VRAM usage, managing model loading/unloading,
and ensuring models are serialized to fit within RTX 4070 8GB constraints.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from loguru import logger

try:
    import torch
    import pynvml
    GPU_AVAILABLE = torch.cuda.is_available()

    if GPU_AVAILABLE:
        try:
            pynvml.nvmlInit()
            NVML_AVAILABLE = True
        except Exception as e:
            logger.warning(f"NVML initialization failed: {e}")
            NVML_AVAILABLE = False
    else:
        NVML_AVAILABLE = False
except ImportError:
    GPU_AVAILABLE = False
    NVML_AVAILABLE = False
    logger.warning("PyTorch or pynvml not available, GPU monitoring disabled")

from config.settings import settings


@dataclass
class GPUStats:
    """GPU statistics snapshot."""

    device_id: int = 0
    total_memory_gb: float = 0.0
    used_memory_gb: float = 0.0
    free_memory_gb: float = 0.0
    utilization_percent: float = 0.0
    temperature_c: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def memory_usage_percent(self) -> float:
        """Calculate memory usage percentage."""
        if self.total_memory_gb > 0:
            return (self.used_memory_gb / self.total_memory_gb) * 100
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "device_id": self.device_id,
            "total_memory_gb": round(self.total_memory_gb, 2),
            "used_memory_gb": round(self.used_memory_gb, 2),
            "free_memory_gb": round(self.free_memory_gb, 2),
            "memory_usage_percent": round(self.memory_usage_percent, 1),
            "utilization_percent": round(self.utilization_percent, 1),
            "temperature_c": self.temperature_c,
            "timestamp": self.timestamp.isoformat(),
        }


class GPUManager:
    """
    Manages GPU resources and monitors memory usage.

    Features:
    - Real-time VRAM monitoring
    - Memory threshold alerts
    - Model usage tracking
    - Automatic cleanup recommendations
    """

    def __init__(
        self,
        device_id: int = 0,
        enable_monitoring: bool = True,
    ):
        """
        Initialize GPU manager.

        Args:
            device_id: CUDA device ID
            enable_monitoring: Enable continuous monitoring
        """
        self.device_id = device_id
        self.enable_monitoring = enable_monitoring and GPU_AVAILABLE

        # Model tracking
        self.loaded_models: Dict[str, datetime] = {}

        # Warning thresholds
        self.max_vram_gb = settings.gpu.max_vram_usage
        self.warning_threshold = settings.gpu.memory_threshold

        if not GPU_AVAILABLE:
            logger.warning("GPU not available, running in CPU mode")
        elif not NVML_AVAILABLE:
            logger.warning("NVML not available, limited GPU monitoring")
        else:
            logger.info(f"GPUManager initialized for device {device_id}")

    def get_stats(self) -> Optional[GPUStats]:
        """
        Get current GPU statistics.

        Returns:
            GPUStats object or None if GPU not available
        """
        if not GPU_AVAILABLE:
            return None

        stats = GPUStats(device_id=self.device_id)

        try:
            # PyTorch memory stats
            if torch.cuda.is_available():
                props = torch.cuda.get_device_properties(self.device_id)
                total_bytes = props.total_memory
                reserved_bytes = torch.cuda.memory_reserved(self.device_id)

                stats.total_memory_gb = total_bytes / (1024 ** 3)
                stats.used_memory_gb = reserved_bytes / (1024 ** 3)
                stats.free_memory_gb = (
                    total_bytes - reserved_bytes
                ) / (1024 ** 3)

            # NVML stats (more detailed)
            if NVML_AVAILABLE:
                handle = pynvml.nvmlDeviceGetHandleByIndex(self.device_id)

                # Memory
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                stats.total_memory_gb = mem_info.total / (1024 ** 3)
                stats.used_memory_gb = mem_info.used / (1024 ** 3)
                stats.free_memory_gb = mem_info.free / (1024 ** 3)

                # Utilization
                utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
                stats.utilization_percent = utilization.gpu

                # Temperature
                try:
                    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                    stats.temperature_c = temp
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Failed to get GPU stats: {e}")
            return None

        return stats

    def check_memory_available(self, required_gb: float) -> bool:
        """
        Check if sufficient memory is available.

        Args:
            required_gb: Required memory in GB

        Returns:
            True if enough memory available
        """
        stats = self.get_stats()
        if not stats:
            return True  # Assume CPU mode is fine

        available = stats.free_memory_gb

        if available < required_gb:
            logger.warning(
                f"Insufficient GPU memory: need {required_gb:.1f}GB, "
                f"have {available:.1f}GB free"
            )
            return False

        return True

    def register_model_loaded(self, model_name: str):
        """
        Register that a model has been loaded.

        Args:
            model_name: Name of the loaded model
        """
        self.loaded_models[model_name] = datetime.utcnow()
        logger.debug(f"Model registered: {model_name}")

        # Log current memory usage
        stats = self.get_stats()
        if stats:
            logger.info(
                f"GPU memory after loading {model_name}: "
                f"{stats.used_memory_gb:.2f}/{stats.total_memory_gb:.2f}GB "
                f"({stats.memory_usage_percent:.1f}%)"
            )

            # Warn if approaching threshold
            if stats.memory_usage_percent > (self.warning_threshold * 100):
                logger.warning(
                    f"GPU memory usage above {self.warning_threshold*100}% threshold"
                )

    def register_model_unloaded(self, model_name: str):
        """
        Register that a model has been unloaded.

        Args:
            model_name: Name of the unloaded model
        """
        if model_name in self.loaded_models:
            del self.loaded_models[model_name]
            logger.debug(f"Model unregistered: {model_name}")

            # Free memory
            if GPU_AVAILABLE:
                torch.cuda.empty_cache()

                stats = self.get_stats()
                if stats:
                    logger.info(
                        f"GPU memory after unloading {model_name}: "
                        f"{stats.used_memory_gb:.2f}/{stats.total_memory_gb:.2f}GB"
                    )

    def get_stale_models(self, max_age_seconds: int = 60) -> list:
        """
        Get models that have been loaded longer than max_age.

        Args:
            max_age_seconds: Maximum age in seconds

        Returns:
            List of stale model names
        """
        stale = []
        cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds)

        for model_name, loaded_at in self.loaded_models.items():
            if loaded_at < cutoff:
                stale.append(model_name)

        return stale

    def clear_cache(self):
        """Clear GPU memory cache."""
        if not GPU_AVAILABLE:
            return

        before = self.get_stats()

        torch.cuda.empty_cache()
        torch.cuda.synchronize()

        after = self.get_stats()

        if before and after:
            freed = before.used_memory_gb - after.used_memory_gb
            logger.info(f"Cleared GPU cache, freed {freed:.2f}GB")

    def get_device_info(self) -> Dict[str, Any]:
        """
        Get GPU device information.

        Returns:
            Device info dictionary
        """
        if not GPU_AVAILABLE:
            return {"available": False, "device": "cpu"}

        info = {
            "available": True,
            "device": f"cuda:{self.device_id}",
            "device_id": self.device_id,
        }

        try:
            props = torch.cuda.get_device_properties(self.device_id)
            info.update({
                "name": props.name,
                "compute_capability": f"{props.major}.{props.minor}",
                "total_memory_gb": props.total_memory / (1024 ** 3),
                "multi_processor_count": props.multi_processor_count,
            })
        except Exception as e:
            logger.warning(f"Failed to get device properties: {e}")

        return info

    def log_summary(self):
        """Log a summary of GPU status."""
        info = self.get_device_info()
        stats = self.get_stats()

        logger.info("=" * 60)
        logger.info("GPU Status Summary")
        logger.info("=" * 60)

        if not info["available"]:
            logger.info("GPU: Not available (using CPU)")
        else:
            logger.info(f"GPU: {info.get('name', 'Unknown')}")
            logger.info(f"Device: {info['device']}")

            if stats:
                logger.info(
                    f"Memory: {stats.used_memory_gb:.2f}/{stats.total_memory_gb:.2f}GB "
                    f"({stats.memory_usage_percent:.1f}% used)"
                )
                logger.info(f"Utilization: {stats.utilization_percent:.1f}%")
                if stats.temperature_c:
                    logger.info(f"Temperature: {stats.temperature_c}°C")

        if self.loaded_models:
            logger.info(f"Loaded models: {len(self.loaded_models)}")
            for model_name, loaded_at in self.loaded_models.items():
                age = (datetime.utcnow() - loaded_at).total_seconds()
                logger.info(f"  - {model_name} (loaded {age:.0f}s ago)")
        else:
            logger.info("No models currently loaded")

        logger.info("=" * 60)


# Global instance
_gpu_manager: Optional[GPUManager] = None


def get_gpu_manager() -> GPUManager:
    """
    Get global GPU manager instance (singleton).

    Returns:
        Shared GPUManager instance
    """
    global _gpu_manager

    if _gpu_manager is None:
        _gpu_manager = GPUManager(
            enable_monitoring=settings.gpu.enable_monitoring
        )

    return _gpu_manager


def reset_gpu_manager():
    """Reset global GPU manager (useful for testing)."""
    global _gpu_manager
    _gpu_manager = None
