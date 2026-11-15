# logging_config.py
import logging
import colorlog

def setup_root_logger(log_level="DEBUG"):
    log_level_obj = getattr(logging, log_level.upper(), logging.DEBUG)

    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        }
    ))
    handler.setLevel(log_level_obj)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level_obj)

    if not root_logger.handlers:
        root_logger.addHandler(handler)
