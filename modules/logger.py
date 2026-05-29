"""
Модуль логирования
"""

import os
import logging
from logging.handlers import RotatingFileHandler

_logger = None
_log_level = "INFO"


def setup_logging(level="INFO"):
    """Настройка логирования в файл и консоль"""
    global _logger, _log_level
    _log_level = level

    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "app.log")

    # Создаём логгер
    _logger = logging.getLogger("license_analyzer")
    _logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    _logger.handlers.clear()

    # Файловый handler с ротацией
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8',
        delay=True  # ← Вот это главное: не открывает файл пока не надо
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    _logger.addHandler(file_handler)

    # Консольный handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(levelname)-8s | %(name)-25s | %(message)s')
    console_handler.setFormatter(console_formatter)
    _logger.addHandler(console_handler)

    # Настройка werkzeug (Flask)
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.handlers.clear()
    werkzeug_logger.addHandler(file_handler)

    return _logger


def get_logger(name):
    """Получает логгер для модуля"""
    if _logger is None:
        setup_logging(_log_level)
    return logging.getLogger(f"license_analyzer.{name}")