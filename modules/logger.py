import os
import glob
import time
import logging
from datetime import datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(_PROJECT_ROOT, "logs")

def clean_old_logs(days=100):
    """Deletes log files older than `days`."""
    now = time.time()
    cutoff = now - (days * 86400)
    
    if not os.path.exists(LOG_DIR):
        return
        
    pattern = os.path.join(LOG_DIR, "*.log")
    for filepath in glob.glob(pattern):
        if os.path.isfile(filepath):
            file_mtime = os.path.getmtime(filepath)
            if file_mtime < cutoff:
                try:
                    os.remove(filepath)
                except Exception as e:
                    print(f"Failed to delete old log {filepath}: {e}")

def get_app_logger(name: str) -> logging.Logger:
    """Returns a logger that writes to a daily file YYYY_MM_DD.log and cleans up old logs."""
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Automatically clean old logs when logger is initialized (useful for daily schedulers)
    clean_old_logs(days=100)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        today_str = datetime.now().strftime("%Y_%m_%d")
        log_file = os.path.join(LOG_DIR, f"{today_str}.log")
        
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
        
        # File handler (utf-8 to handle any unicode characters safely)
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        
        # Console handler
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
    return logger
