"""Centralized loguru configuration."""
import sys
from loguru import logger


def configure_logging(level: str = "INFO", json_logs: bool = False):
    logger.remove()

    if json_logs:
        logger.add(
            sys.stdout,
            level=level,
            serialize=True,
            enqueue=True,
        )
    else:
        logger.add(
            sys.stdout,
            level=level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>",
            enqueue=True,
            colorize=True,
        )

    logger.add(
        "logs/campus_sentinel.log",
        rotation="100 MB",
        retention="7 days",
        compression="gz",
        level="DEBUG",
        enqueue=True,
    )

    return logger
