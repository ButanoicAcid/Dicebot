import logging
from logging import FileHandler
from pathlib import Path

level_dict = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def get_logger(
    name: str,
    sessionid: str,
    filename: str,
    directory: Path,
    level: str,
) -> logging.Logger:

    logger = logging.getLogger(f"{name}.{sessionid}")

    if logger.handlers:
        return logger

    try:
        loggerlevel = level_dict[level.upper()]
    except KeyError:
        raise ValueError(f"Unknown log level: {level}")

    directory.mkdir(parents=True, exist_ok=True)

    handler = FileHandler(
        directory / f"{filename}.log",
        mode="w",
        encoding="utf-8",
    )

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler.setFormatter(formatter)

    logger.setLevel(loggerlevel)
    logger.addHandler(handler)
    logger.propagate = False

    return logger
