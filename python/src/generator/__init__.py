"""
Database generator module for the DB Simulator.
Provides functionality to generate synthetic SQLite databases
from configuration files.
"""

import os
import logging
from pathlib import Path

from .database_generator import DatabaseGenerator
from ..config_parser import parse_db_config, parse_sim_config, parse_db_config_from_string, parse_sim_config_from_string
from ..utils.path_resolver import resolve_output_dir

# Create logger
logger = logging.getLogger(__name__)

def generate_database(config_path_or_content, output_dir='output', db_name=None, project_id=None, sim_config_path_or_content=None, project_dir=None):
    """
    Generate a SQLite database from a configuration file path or content string.
    Returns only the database path.
    """
    db_path, _ = _generate_database_internal(
        config_path_or_content,
        output_dir,
        db_name,
        project_id,
        sim_config_path_or_content,
        project_dir,
    )
    return db_path


def generate_database_with_formula_support(config_path_or_content, output_dir='output', db_name=None, project_id=None, sim_config_path_or_content=None, project_dir=None):
    """
    Generate a SQLite database and return both path and generator (for post-simulation formula resolution).
    """
    return _generate_database_internal(
        config_path_or_content,
        output_dir,
        db_name,
        project_id,
        sim_config_path_or_content,
        project_dir,
    )


def _generate_database_internal(config_path_or_content, output_dir, db_name, project_id, sim_config_path_or_content, project_dir=None):
    """Shared implementation for database generation."""
    # Parse DB config
    if os.path.exists(config_path_or_content) and os.path.isfile(config_path_or_content):
        logger.info(f"Generating database from config file: {config_path_or_content}")
        config = parse_db_config(config_path_or_content)
    else:
        logger.info("Generating database from config content string")
        config = parse_db_config_from_string(config_path_or_content)

    # Parse simulation config if provided
    sim_config = None
    if sim_config_path_or_content:
        if os.path.exists(sim_config_path_or_content) and os.path.isfile(sim_config_path_or_content):
            logger.info(f"Parsing simulation config from file: {sim_config_path_or_content}")
            sim_config = parse_sim_config(sim_config_path_or_content)
        else:
            logger.info("Parsing simulation config from content string")
            sim_config = parse_sim_config_from_string(sim_config_path_or_content)
    else:
        logger.debug("No simulation config provided")

    # Resolve output directory (env/project-aware)
    output_dir = resolve_output_dir(output_dir, project_id)

    # Generate a database name if not provided
    if not db_name:
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        db_name = f"generated_db_{timestamp}"
        logger.info(f"Generated database name: {db_name}")
    else:
        logger.info(f"Using provided database name: {db_name}")

    # Strip .db extension if used
    if db_name.endswith('.db'):
        db_name = db_name[:-3]
        logger.info(f"Removed .db extension from database name: {db_name}")

    generator = DatabaseGenerator(config, output_dir, None, sim_config, project_dir=project_dir)
    db_path = generator.generate(db_name)

    # Ensure the returned path is absolute
    if not os.path.isabs(db_path):
        db_path = os.path.abspath(db_path)

    # Verify the database file exists
    if os.path.exists(db_path):
        file_size = os.path.getsize(db_path)
        logger.info(f"Generated database at path: {db_path} (size: {file_size} bytes)")
        if file_size == 0:
            logger.warning("Generated database file is empty (0 bytes)")
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            logger.info(f"Database contains {len(tables)} tables: {[t[0] for t in tables]}")
            conn.close()
        except Exception as e:
            logger.error(f"Error verifying database: {e}")
    else:
        logger.error(f"Database file does not exist at expected path: {db_path}")
        try:
            logger.info(f"Files in output directory {output_dir}:")
            for f in os.listdir(output_dir):
                file_path = os.path.join(output_dir, f)
                if os.path.isfile(file_path):
                    logger.info(f"  - {f} ({os.path.getsize(file_path)} bytes)")
                else:
                    logger.info(f"  - {f} (directory)")
        except Exception as dir_error:
            logger.error(f"Error listing directory contents: {dir_error}")

    return db_path, generator

__all__ = [
    'generate_database',
    'generate_database_with_formula_support',
    'DatabaseGenerator'
]
