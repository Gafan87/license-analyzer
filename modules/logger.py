import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = "logs"

def setup_logging(level='INFO'):
    """Настройка системы логирования"""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    
    levels = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR
    }
    
    log_level = levels.get(level, logging.INFO)
    
    # Закрываем существующие handler'ы
    for handler in logging.root.handlers[:]:
        handler.close()
        logging.root.removeHandler(handler)
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Используем delay=True для отложенного создания файла
    file_handler = RotatingFileHandler(
        f'{LOG_DIR}/app.log', 
        maxBytes=5*1024*1024, 
        backupCount=5,
        encoding='utf-8',
        delay=True  # ← Добавить delay=True
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
    ))
    logging.root.addHandler(file_handler)
    
    error_handler = RotatingFileHandler(
        f'{LOG_DIR}/error.log', 
        maxBytes=5*1024*1024, 
        backupCount=5,
        encoding='utf-8',
        delay=True  # ← Добавить delay=True
    )
    error_handler.setLevel(logging.ERROR)
    logging.root.addHandler(error_handler)
    
    logging.info(f"Логирование настроено. Уровень: {level}")

def get_logger(name):
    return logging.getLogger(name)