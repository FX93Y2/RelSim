"""
Main entry point for both API and CLI
"""

import argparse
import logging
import sys
import os

# Import components from refactored structure
from src.generator import generate_database, generate_database_with_formula_support
from src.simulation.core.runner import run_simulation, run_simulation_from_config_dir
from config_storage.config_db import ConfigManager

# Import the Flask app factory from refactored API server
# Import the Flask app factory from refactored API server
from api.server import create_app

# Apply py_mini_racer patch for Windows support
import patch_mini_racer
patch_mini_racer.apply_patch()

# Configure logging (console)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Optional file logging if Electron passes a log file path
_log_file = os.environ.get('DB_SIMULATOR_LOG_FILE')
if _log_file:
    try:
        fh = logging.FileHandler(_log_file, encoding='utf-8')
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        root_logger = logging.getLogger()
        root_logger.addHandler(fh)
        root_logger.info('File logging enabled at %s', _log_file)
    except Exception as _e:
        logging.getLogger(__name__).warning('Failed to enable file logging: %s', _e)
logger = logging.getLogger(__name__)

# Initialize the Flask app using the modular structure
app = create_app()

# Initialize configuration manager (for CLI usage)
config_manager = ConfigManager()

# All API routes are now handled by the modular routes structure in api/routes/
# This file now only handles CLI functionality

def run_api(host='127.0.0.1', port=5001):
    """Run the Flask API server"""
    app.run(host=host, port=port, debug=False)

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description='DB Simulator')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # API server command
    api_parser = subparsers.add_parser('api', help='Start the API server')
    api_parser.add_argument('--host', default='127.0.0.1', help='Host to bind the API server')
    api_parser.add_argument('--port', type=int, default=5001, help='Port to bind the API server')
    
    # Added for PyInstaller compatibility - will be passed by Electron
    api_parser.add_argument('--output-dir', help='Output directory for files')
    api_parser.add_argument('--config-db', help='Path to config database')
    api_parser.add_argument('--packaged', help='Whether running in packaged mode')
    
    # Generate database command (preserved for CLI compatibility)
    gen_parser = subparsers.add_parser('generate', help='Generate a synthetic database')
    gen_parser.add_argument('config', help='Path to database configuration file')
    gen_parser.add_argument('--output-dir', '-o', default='output', help='Output directory')
    gen_parser.add_argument('--name', '-n', help='Database name (without extension)')
    gen_parser.add_argument('--sim-config', help='Path to simulation configuration file for attribute column detection')
    
    # Run simulation command (preserved for CLI compatibility)
    sim_parser = subparsers.add_parser('simulate', help='Run a simulation')
    sim_parser.add_argument('config', help='Path to simulation configuration file')
    sim_parser.add_argument('db_config', help='Path to database configuration file')
    sim_parser.add_argument('database', help='Path to SQLite database file')
    
    # Generate resources and run simulation command
    dynamic_parser = subparsers.add_parser('dynamic-simulate', 
                                          help='[DEPRECATED] Generate a database with only resource tables and run a simulation (use generate-simulate instead)')
    dynamic_parser.add_argument('db_config', help='Path to database configuration file')
    dynamic_parser.add_argument('sim_config', help='Path to simulation configuration file')
    dynamic_parser.add_argument('--output-dir', '-o', default='output', help='Output directory')
    dynamic_parser.add_argument('--name', '-n', help='Database name (without extension)')
    
    # New command that properly handles relationship columns
    gen_sim_parser = subparsers.add_parser('generate-simulate',
                                         help='Generate a complete database and run a simulation with proper table relationships')
    gen_sim_parser.add_argument('db_config', help='Path to database configuration file')
    gen_sim_parser.add_argument('sim_config', help='Path to simulation configuration file')
    gen_sim_parser.add_argument('--output-dir', '-o', default='output', help='Output directory')
    gen_sim_parser.add_argument('--name', '-n', help='Database name (without extension)')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Handle environment variables for compatibility
    if args.command == 'api':
        # Set environment variables from args for backward compatibility
        if args.output_dir:
            os.environ['DB_SIMULATOR_OUTPUT_DIR'] = args.output_dir
            
        if args.config_db:
            os.environ['DB_SIMULATOR_CONFIG_DB'] = args.config_db
            
        if args.packaged:
            os.environ['DB_SIMULATOR_PACKAGED'] = args.packaged
            
        # Log the environment variables for debugging
        logger.info(f"Running with output_dir: {os.environ.get('DB_SIMULATOR_OUTPUT_DIR', 'not set')}")
        logger.info(f"Running with config_db: {os.environ.get('DB_SIMULATOR_CONFIG_DB', 'not set')}")
        logger.info(f"Running in packaged mode: {os.environ.get('DB_SIMULATOR_PACKAGED', 'not set')}")
        
        run_api(host=args.host, port=args.port)
    elif args.command == 'generate':
        try:
            db_path = generate_database(args.config, args.output_dir, args.name, sim_config_path_or_content=args.sim_config)
            logger.info(f"Database generated at: {db_path}")
        except Exception as e:
            logger.error(f"Error generating database: {e}")
            sys.exit(1)
    elif args.command == 'simulate':
        try:
            # Pass sim config path, db config path, and db path
            results = run_simulation(args.config, args.db_config, args.database)
            logger.info(f"Simulation results: {results}")
        except Exception as e:
            logger.error(f"Error running simulation: {e}")
            sys.exit(1)
    elif args.command == 'dynamic-simulate':
        logger.warning("The 'dynamic-simulate' command is deprecated and may be removed in future versions. Please use 'generate-simulate' instead.")
        try:
            # Use generate_database instead of generate_database_for_simulation for better reliability
            db_path = generate_database(args.db_config, args.output_dir, args.name, sim_config_path=args.sim_config)
            logger.info(f"Database generated at: {db_path}")
            
            # Run simulation with dynamic entity generation
            results = run_simulation(args.sim_config, args.db_config, db_path)
            logger.info(f"Simulation results: {results}")
        except Exception as e:
            logger.error(f"Error in dynamic simulation: {e}")
            sys.exit(1)
    elif args.command == 'generate-simulate':
        try:
            # This command fixes the relationship column issue by:
            # 1. Creating a full database with all tables (not just resources)
            # 2. Running the simulation on this complete database
            
            # Generate complete database with all tables and run simulation with formula support
            db_path, generator = generate_database_with_formula_support(
                args.db_config, 
                args.output_dir, 
                args.name, 
                sim_config_path_or_content=args.sim_config
            )
            logger.info(f"Complete database generated at: {db_path}")
            
            # Run simulation on the complete database
            results = run_simulation(args.sim_config, args.db_config, db_path)
            logger.info(f"Simulation results: {results}")
            
            # Resolve formulas after simulation if any are pending
            if generator.has_pending_formulas():
                logger.info("Resolving formula-based attributes after simulation")
                success = generator.resolve_formulas(db_path)
                if success:
                    logger.info("Formula resolution completed successfully")
                else:
                    logger.error("Formula resolution failed")
            else:
                logger.info("No formula attributes found, skipping formula resolution")
        except Exception as e:
            logger.error(f"Error in generate-simulate: {e}")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main() 
