"""
Database generation routes for DB Simulator API.
Handles database generation operations.
"""

import logging
import sys
import os

# Add parent directory to sys.path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from flask import Blueprint, request
from config_storage.config_db import ConfigManager
from src.generator import generate_database
from src.utils.path_resolver import resolve_output_dir
from ..utils.response_helpers import (
    success_response, error_response, not_found_response, validation_error_response,
    handle_exception, require_json_fields, log_api_request
)
from ..utils.run_logger import run_log_context

# Create Blueprint
database_bp = Blueprint('database', __name__)

# Initialize configuration manager
config_manager = ConfigManager()

# Create logger
logger = logging.getLogger(__name__)

@database_bp.route('/generate-database', methods=['POST'])
def generate_db():
    """Generate a synthetic database"""
    try:
        log_api_request(logger, "Generate database")
        
        # Validate request data
        data, validation_error = require_json_fields(request, ['config_id'])
        if validation_error:
            return validation_error
        
        config = config_manager.get_config(data['config_id'])
        if not config:
            return not_found_response("Configuration")
        
        output_dir = data.get('output_dir', 'output')
        db_name = data.get('name')
        project_id = data.get('project_id')
        
        # Pass configuration content directly to generate_database
        project_dir = resolve_output_dir(project_id=project_id) if project_id else None
        logger.info(f"Generating database directly from config content (project_id={project_id}, project_dir={project_dir})")
        with run_log_context(project_id=project_id, db_name=db_name):
            db_path = generate_database(config['content'], output_dir, db_name, project_id, project_dir=project_dir)
        
        # Build a relative path for the frontend (matches scanProjectResults format)
        db_filename = os.path.basename(db_path)
        if project_id:
            db_path_for_response = f"output/{project_id}/{db_filename}"
        else:
            db_path_for_response = f"output/{db_filename}"
        db_path_for_response = db_path_for_response.replace('\\', '/')
        
        logger.info(f"Database generated. Absolute: {db_path}, Response: {db_path_for_response}")
        
        return success_response({
            "database_path": db_path_for_response
        }, message=f"Database generated at: {db_path_for_response}")
        
    except Exception as e:
        return handle_exception(e, "generating database", logger)