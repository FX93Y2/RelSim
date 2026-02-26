"""
Simulation execution routes for DB Simulator API.
Handles simulation running and generate-and-simulate operations.
"""

import logging
import sys
import os
import gc
import time

# Add parent directory to sys.path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from flask import Blueprint, request
from config_storage.config_db import ConfigManager
from src.generator import generate_database
from src.simulation.core.runner import run_simulation
from src.utils.file_operations import safe_delete_sqlite_file
from src.utils.path_resolver import resolve_output_dir
from ..utils.response_helpers import (
    success_response, error_response, not_found_response, validation_error_response,
    handle_exception, require_json_fields, log_api_request
)
from ..utils.run_logger import run_log_context

# Create Blueprint
simulation_bp = Blueprint('simulation', __name__)

# Initialize configuration manager
config_manager = ConfigManager()

# Create logger
logger = logging.getLogger(__name__)

@simulation_bp.route('/run-simulation', methods=['POST'])
def run_sim():
    """Run a simulation on an existing database"""
    try:
        log_api_request(logger, "Run simulation")
        
        # Validate request data
        data, validation_error = require_json_fields(request, ['config_id', 'database_path'])
        if validation_error:
            return validation_error
        
        config = config_manager.get_config(data['config_id'])
        if not config:
            return not_found_response("Configuration")
        
        # Get database config if available
        db_config_id = data.get('db_config_id')
        db_config_content = None
        
        if db_config_id:
            db_config = config_manager.get_config(db_config_id)
            if db_config:
                db_config_content = db_config['content']
        
        # Derive project_id and db_name for per-run log placement
        project_id = data.get('project_id')
        db_name = os.path.splitext(os.path.basename(data['database_path']))[0]

        # Run simulation with database config if available
        with run_log_context(project_id=project_id, db_name=db_name):
            if db_config_content:
                results = run_simulation(config['content'], db_config_content, data['database_path'])
            else:
                # Fallback to old method for backward compatibility
                results = run_simulation(config['content'], data['database_path'])
        
        return success_response({
            "results": results
        }, message="Simulation completed successfully")
        
    except Exception as e:
        return handle_exception(e, "running simulation", logger)

@simulation_bp.route('/generate-and-simulate', methods=['POST'])
def generate_and_simulate():
    """Generate a database and run a simulation"""
    try:
        log_api_request(logger, "Generate and simulate")
        
        # Validate request data
        data, validation_error = require_json_fields(request, ['db_config_id', 'sim_config_id'])
        if validation_error:
            return validation_error
        
        db_config = config_manager.get_config(data['db_config_id'])
        sim_config = config_manager.get_config(data['sim_config_id'])
        
        if not db_config or not sim_config:
            return not_found_response("Configuration")
        
        # Determine output directory
        output_dir = _determine_output_directory()
        project_id = data.get('project_id')
        db_name = data.get('name')
        
        # Delete existing database file if it exists
        _cleanup_existing_database(output_dir, project_id, db_name, db_config)
        
        with run_log_context(project_id=project_id, db_name=db_name):
            # Generate database with simulation config for attribute detection
            logger.info(f"Generating database with project_id: {project_id}")
            from src.generator import generate_database_with_formula_support
            db_path, generator = generate_database_with_formula_support(
                db_config['content'], 
                output_dir,
                db_name,
                project_id,
                sim_config['content']  # Pass simulation config content for attribute column detection
            )
            
            # Verify database creation
            if not _verify_database_creation(db_path):
                return error_response(f"Failed to create database file at {db_path}", status_code=500)
            
            # Run simulation
            logger.info(f"Running simulation using database at: {db_path}")
            results = run_simulation(
                sim_config['content'],
                db_config['content'],
                db_path
            )
            
            # Resolve formula attributes after simulation (transparent to user)
            if generator.has_pending_formulas():
                logger.info("Resolving formula-based attributes after simulation completion")
                formula_success = generator.resolve_formulas(db_path)
                if formula_success:
                    logger.info("Formula resolution completed successfully")
                else:
                    logger.warning("Formula resolution failed, but continuing with simulation results")
        
        # Verify database after simulation and prepare response path
        db_path_for_response = _prepare_response_path(db_path, output_dir, project_id)
        
        return success_response({
            "database_path": db_path_for_response,
            "results": results
        }, message="Generate-and-simulate completed successfully")
        
    except Exception as e:
        return handle_exception(e, "generate-and-simulate", logger)

@simulation_bp.route('/force-cleanup', methods=['POST'])
def force_cleanup():
    """
    Force cleanup of database connections and resources.
    This is a workaround for EBUSY errors on Windows caused by persistent connections.
    """
    try:
        log_api_request(logger, "Force cleanup")
        
        # Force garbage collection to clean up any lingering objects
        gc.collect()
        
        # Give a small delay for OS to release handles
        time.sleep(0.1)
        
        logger.info("Forced cleanup completed")
        return success_response(message='Cleanup completed successfully')
        
    except Exception as e:
        return handle_exception(e, "forced cleanup", logger)

def _determine_output_directory():
    """Determine the appropriate output directory using shared resolver."""
    return resolve_output_dir()

def _cleanup_existing_database(output_dir, project_id, db_name, db_config):
    """Clean up existing database file before generation."""
    try:
        # Construct preliminary path to check for existence before generation logic determines final name
        preliminary_db_name = db_name or db_config.get('name', 'database')  # Use provided name or fallback
        if not preliminary_db_name.endswith('.db'):
            preliminary_db_name += '.db'
            
        target_dir = os.path.join(output_dir, project_id) if project_id else output_dir
        preliminary_db_path = os.path.join(target_dir, preliminary_db_name)
        
        logger.info(f"Checking for existing database file at: {preliminary_db_path}")
        if not safe_delete_sqlite_file(preliminary_db_path):
            logger.warning(f"Could not safely delete existing database file: {preliminary_db_path}")
    except Exception as del_err:
        logger.error(f"Error trying to delete existing database file: {del_err}")

def _verify_database_creation(db_path):
    """Verify that the database was created successfully."""
    if os.path.exists(db_path):
        file_size = os.path.getsize(db_path)
        logger.info(f"Database file created successfully: {db_path}, size: {file_size} bytes")
        
        # Log directory contents for debugging
        db_dir = os.path.dirname(db_path)
        if os.path.exists(db_dir):
            logger.info(f"Contents of database directory {db_dir}:")
            for f in os.listdir(db_dir):
                file_path = os.path.join(db_dir, f)
                if os.path.isfile(file_path):
                    logger.info(f"  - {f} ({os.path.getsize(file_path)} bytes)")
        return True
    else:
        logger.error(f"Database file was not created at expected path: {db_path}")
        return False

def _prepare_response_path(db_path, output_dir, project_id):
    """Prepare the database path for the API response."""
    # Verify database file after simulation
    if os.path.exists(db_path):
        file_size = os.path.getsize(db_path)
        logger.info(f"Database file exists after simulation: {db_path}, size: {file_size} bytes")
        
        # Verify database has tables and content
        _verify_database_content(db_path)
        
        # Create a relative path for the frontend to use
        db_filename = os.path.basename(db_path)
        
        # For project-specific path
        if project_id:
            relative_path = f"output/{project_id}/{db_filename}"
        else:
            relative_path = f"output/{db_filename}"
            
        logger.info(f"Using relative path for frontend: {relative_path}")
        db_path_for_response = relative_path
    else:
        logger.error(f"Database file not found after simulation: {db_path}")
        # Try to find the file by pattern matching
        db_path_for_response = _find_alternative_database(db_path, project_id)
    
    # Make sure path uses forward slashes for consistent handling in frontend
    db_path_for_response = db_path_for_response.replace('\\', '/')
    
    # Final verification
    _final_path_verification(db_path, db_path_for_response, output_dir)
    
    return db_path_for_response

def _verify_database_content(db_path):
    """Verify database has tables and content."""
    conn = None
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        logger.info(f"Database contains {len(tables)} tables: {[t[0] for t in tables]}")
        
        # Count rows in a few key tables
        for table_name in [t[0] for t in tables]:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM \"{table_name}\"")
                count = cursor.fetchone()[0]
                logger.info(f"Table '{table_name}' has {count} rows")
            except Exception as e:
                logger.error(f"Error counting rows in table '{table_name}': {e}")
        
    except Exception as e:
        logger.error(f"Error verifying database content: {e}")
    finally:
        # ALWAYS close the database connection to prevent EBUSY errors on Windows
        if conn:
            try:
                conn.close()
                logger.debug(f"Database verification connection closed for: {db_path}")
            except Exception as close_err:
                logger.warning(f"Error closing verification connection: {close_err}")

def _find_alternative_database(db_path, project_id):
    """Find alternative database file if the expected one doesn't exist."""
    expected_dir = os.path.dirname(db_path)
    if os.path.exists(expected_dir):
        files = os.listdir(expected_dir)
        db_files = [f for f in files if f.endswith('.db')]
        if db_files:
            logger.info(f"Found alternative database files in directory: {db_files}")
            
            # Use the first database file found as a fallback
            alternative_db = os.path.join(expected_dir, db_files[0])
            logger.info(f"Using alternative database file: {alternative_db}")
            
            # Create a relative path for the frontend
            if project_id:
                relative_path = f"output/{project_id}/{db_files[0]}"
            else:
                relative_path = f"output/{db_files[0]}"
                
            logger.info(f"Using alternative relative path for frontend: {relative_path}")
            return relative_path
        else:
            logger.error(f"No database files found in directory: {expected_dir}")
            return str(db_path)
    else:
        logger.error(f"Expected directory does not exist: {expected_dir}")
        return str(db_path)

def _final_path_verification(db_path, db_path_for_response, output_dir):
    """Perform final verification that the database file exists."""
    try:
        # Try different ways of resolving the path
        potential_paths = [
            db_path,  # Original absolute path
            db_path_for_response,  # Relative path for frontend
            os.path.join(output_dir, db_path_for_response.replace('output/', ''))  # Resolved from output dir
        ]
        
        # Check if any of these paths exist
        found = False
        for path in potential_paths:
            if os.path.exists(path):
                logger.info(f"Final verification: Database exists at: {path}")
                found = True
                break
        
        if not found:
            logger.warning("Final verification: Database file not found at any expected location")
    except Exception as e:
        logger.error(f"Error in final verification: {e}")
