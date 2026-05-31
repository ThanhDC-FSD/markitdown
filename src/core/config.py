"""
Configuration for RAG Pipeline - Logging, Ports, and Processing Parameters
"""

import json
import os
import logging
from pathlib import Path
from datetime import datetime

# ============================================================================
# DIRECTORIES
# ============================================================================
PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = Path(__file__).parent
LOGS_DIR = PROJECT_ROOT / "logs"
DATA_DIR = PROJECT_ROOT / "data"
CHROMA_DB_DIR = Path(os.getenv("CHROMA_DB_DIR", str(PROJECT_ROOT / "chroma_db")))

# Create directories if they don't exist
LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
CHROMA_DB_DIR.mkdir(exist_ok=True)

# ============================================================================
# API CONFIGURATION
# ============================================================================
API_HOST = "0.0.0.0"
API_PORT = 8001  # Changed from 8000 to avoid conflict with Copilot API
API_URL = f"http://localhost:{API_PORT}"
DOCS_URL = f"{API_URL}/docs"

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Log files
API_LOG_FILE = LOGS_DIR / f"api_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
DEMO_LOG_FILE = LOGS_DIR / f"demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
PIPELINE_LOG_FILE = LOGS_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# ============================================================================
# DOCUMENT PROCESSING CONFIGURATION
# ============================================================================
CHUNK_SIZE = 512  # Characters per chunk
CHUNK_OVERLAP = 64  # Overlap between chunks
MAX_CHUNKS_PER_DOCUMENT = 500  # Prevent memory issues with huge docs

# Chunking strategies
CHUNK_METHOD = "sentences"  # Options: "sentences", "tokens", "semantic"
MIN_CHUNK_SIZE = 100  # Minimum characters per chunk
MAX_CHUNK_SIZE = 1024  # Maximum characters per chunk

# ============================================================================
# RETRIEVAL CONFIGURATION
# ============================================================================
TOP_K_RETRIEVAL = 5  # Top-K similar documents to retrieve
RERANK_TOP_K = 3  # Top-K after re-ranking
SIMILARITY_THRESHOLD = 0.3  # Minimum similarity score

# ============================================================================
# GROUNDED QA / COPILOT CONFIGURATION
# ============================================================================


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_json(name: str, default):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        parsed = json.loads(value)
        if isinstance(default, dict) and isinstance(parsed, dict):
            return parsed
        if isinstance(default, list) and isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    return default


COPILOT_API_BASE_URL = os.getenv("COPILOT_API_BASE_URL", "http://localhost:8080").rstrip("/")
GROUNDED_QA_ENDPOINT = os.getenv("GROUNDED_QA_ENDPOINT", "/qa/answer")
if not GROUNDED_QA_ENDPOINT.startswith("/"):
    GROUNDED_QA_ENDPOINT = f"/{GROUNDED_QA_ENDPOINT}"

DEFAULT_GROUNDED_MODEL = os.getenv("DEFAULT_GROUNDED_MODEL", "gpt-5-mini")
DEFAULT_GROUNDED_ANSWER_POLICY = _env_json(
    "DEFAULT_GROUNDED_ANSWER_POLICY",
    {
        "grounded_only": True,
        "allow_light_semantic_inference": True,
        "abstain_if_insufficient": True,
        "return_citations": True,
        "max_answer_sentences": 4,
        "forbidden_topics": [],
    },
)
DEFAULT_GROUNDED_GENERATION_OPTIONS = _env_json(
    "DEFAULT_GROUNDED_GENERATION_OPTIONS",
    {
        "temperature": 0.2,
        "stream": False,
        "top_p": 1,
    },
)
COPILOT_API_TIMEOUT_SECONDS = _env_float("COPILOT_API_TIMEOUT_SECONDS", 30.0)
COPILOT_API_RETRY_COUNT = _env_int("COPILOT_API_RETRY_COUNT", 1)
COPILOT_API_RETRY_BACKOFF_SECONDS = _env_float("COPILOT_API_RETRY_BACKOFF_SECONDS", 0.5)
COPILOT_API_USER_AGENT = os.getenv("COPILOT_API_USER_AGENT", "markitdown-rag-server/1.0")

# Preserve the intent analyzer threshold used by the query flow.
DEFAULT_ALLOW_LIGHT_SEMANTIC_INFERENCE = _env_bool("DEFAULT_ALLOW_LIGHT_SEMANTIC_INFERENCE", True)

# ============================================================================
# INTENT ANALYSIS CONFIGURATION
# ============================================================================
RELEVANCE_THRESHOLD = 0.2  # Minimum relevance score to consider KB relevant

# ============================================================================
# LOGGING SETUP FUNCTION
# ============================================================================

def setup_logger(name: str, log_file: Path = None) -> logging.Logger:
    """
    Set up a logger with both file and console handlers.
    
    Args:
        name: Logger name (typically __name__)
        log_file: Optional log file path. If None, only console output.
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(LOG_LEVEL)
    console_formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler (if log file specified)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(LOG_LEVEL)
        file_formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        logger.info(f"Logging to {log_file}")
    
    return logger


# ============================================================================
# DEBUG INFO
# ============================================================================
if __name__ == "__main__":
    logger = setup_logger(__name__, PIPELINE_LOG_FILE)
    logger.info(f"Project root: {PROJECT_ROOT}")
    logger.info(f"Logs directory: {LOGS_DIR}")
    logger.info(f"ChromaDB directory: {CHROMA_DB_DIR}")
    logger.info(f"API will run at: {API_URL}/docs")
