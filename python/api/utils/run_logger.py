"""
Per-run file logging context manager.

Temporarily attaches a FileHandler to the root logger for the duration of
a single generation / simulation run so that each run gets its own log file
stored alongside the database it produced.

Usage:
    from api.utils.run_logger import run_log_context

    with run_log_context(project_id=project_id, db_name=db_name):
        run_simulation(...)
"""

import contextlib
import logging
import os
from datetime import datetime

from src.utils.path_resolver import resolve_output_dir

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def run_log_context(project_id: "str | None", db_name: "str | None"):
    """
    Temporarily attach a per-run FileHandler to the root logger.

    The log is written to:
        <output_dir>/<project_id>/logs/<db_name>_<YYYYMMDD_HHMMSS>.log

    When no project_id is given the log lands in:
        <output_dir>/logs/<db_name>_<YYYYMMDD_HHMMSS>.log

    The handler is removed and closed in a finally block so the root logger
    is never left in a dirty state even if the run raises an exception.
    """
    db_label = (db_name or "run").replace("/", "_").replace("\\", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{db_label}_{timestamp}.log"

    # Resolve the project output dir (mirrors where the .db file lands)
    project_dir = resolve_output_dir(project_id=project_id)
    logs_dir = os.path.join(project_dir, "logs")

    handler = None
    log_path = None
    try:
        os.makedirs(logs_dir, exist_ok=True)
        log_path = os.path.join(logs_dir, log_filename)

        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

        root = logging.getLogger()
        root.addHandler(handler)
        root.info("=== Run log started: %s ===", log_path)
        logger.info("Per-run log file: %s", log_path)
    except Exception as setup_err:
        logger.warning("Could not create per-run log file: %s", setup_err)
        # Yield anyway — the run still proceeds, just without the extra log
        yield None
        return

    try:
        yield log_path
    finally:
        try:
            logging.getLogger().info("=== Run log ended: %s ===", log_path)
        except Exception:
            pass
        try:
            logging.getLogger().removeHandler(handler)
            handler.close()
        except Exception as teardown_err:
            logger.warning("Error closing per-run log handler: %s", teardown_err)
