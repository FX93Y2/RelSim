"""
Simulation runner module.

This module provides functions to run simulations from configuration files.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Union

from ...config_parser import parse_sim_config, parse_sim_config_from_string
from ...config_parser import parse_db_config, parse_db_config_from_string # Import db config parsers
from .simulator import EventSimulator

logger = logging.getLogger(__name__)

def ensure_simulation_tables(sim_config, db_path: Union[str, Path], db_config=None):
    """
    Ensure that the necessary tables for simulation exist in the database
    
    Args:
        sim_config: Simulation configuration
        db_path: Path to the SQLite database
        db_config: Optional database configuration
    """
    if not sim_config.event_simulation:
        return
    
    # Event tables are no longer provisioned; nothing to ensure here.
    return

# Add a call to ensure_simulation_tables in run_simulation
def run_simulation(sim_config_path_or_content: Union[str, Path],
                   db_config_path_or_content: Union[str, Path],
                   db_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Run a simulation based on configuration, ensuring required tables exist.
    
    Args:
        sim_config_path_or_content: Path to the simulation configuration file or YAML content string
        db_config_path_or_content: Path to the database configuration file or YAML content string.
        db_path: Path to the SQLite database
        
    Returns:
        Dictionary with simulation results
    """
    # Parse database configuration first
    db_config = None
    if isinstance(db_config_path_or_content, (str, Path)) and os.path.exists(db_config_path_or_content) and os.path.isfile(db_config_path_or_content):
        logger.info(f"Parsing database config file: {db_config_path_or_content}")
        db_config = parse_db_config(db_config_path_or_content)
    elif isinstance(db_config_path_or_content, str):
        logger.info("Parsing database config from content string")
        db_config = parse_db_config_from_string(db_config_path_or_content)
    else:
        raise ValueError("Invalid db_config_path_or_content provided.")
        
    # Parse simulation configuration with database config
    sim_config = None
    if isinstance(sim_config_path_or_content, (str, Path)) and os.path.exists(sim_config_path_or_content) and os.path.isfile(sim_config_path_or_content):
        logger.info(f"Parsing simulation config file: {sim_config_path_or_content}")
        sim_config = parse_sim_config(sim_config_path_or_content, db_config)
    elif isinstance(sim_config_path_or_content, str):
        logger.info("Parsing simulation config from content string")
        sim_config = parse_sim_config_from_string(sim_config_path_or_content, db_config)
    else:
        raise ValueError("Invalid sim_config_path_or_content provided.")
    
    # Ensure necessary tables exist
    ensure_simulation_tables(sim_config, db_path, db_config)
    
    # Create and run simulator
    logger.info("Initializing EventSimulator...")
    simulator = EventSimulator(config=sim_config, db_config=db_config, db_path=db_path)
    results = simulator.run()
    
    # Post-simulation hooks: run any post-processing that cannot be
    # expressed in the declarative YAML (e.g., multi-row conditional chaining)
    _run_post_simulation_hooks(db_path, db_config)
    
    logger.info(f"Simulation completed: {results}")
    return results


def _run_post_simulation_hooks(db_path, db_config=None):
    """
    Run post-simulation processing hooks.
    
    Currently handles:
    - Consultant_Title_History: complex promotion-chain logic (1-3 rows
      per consultant with sequential dates and title-dependent salaries)
    - Deliverable_Progress_Month: monthly progress records derived from
      Consultant_Deliverable_Mapping date ranges
    """
    if not db_config:
        return
    
    entity_names = [e.name for e in db_config.entities]
    
    # Lazy import setup (only done once)
    import sys
    from pathlib import Path
    # Go 4 levels up: runner.py → core/ → simulation/ → src/ → python/
    python_dir = str(Path(__file__).resolve().parent.parent.parent.parent)
    if python_dir not in sys.path:
        sys.path.insert(0, python_dir)
    
    # Hook 1: Consultant_Title_History
    if 'Consultant_Title_History' in entity_names:
        try:
            from generate_title_history import populate_title_history
            
            logger.info("Running post-simulation hook: Consultant_Title_History")
            count = populate_title_history(str(db_path))
            if count > 0:
                logger.info(f"Post-simulation hook: generated {count} title history records")
            elif count == 0:
                logger.warning("Post-simulation hook: no title history records generated")
            else:
                logger.error("Post-simulation hook: title history generation failed")
        except ImportError:
            logger.warning(
                "Post-simulation hook: generate_title_history module not found. "
                "Run 'python generate_title_history.py' manually."
            )
        except Exception as e:
            logger.error(f"Post-simulation hook (title history) error: {e}")
    
    # Hook 2: Deliverable_Progress_Month
    if 'Deliverable_Progress_Month' in entity_names:
        try:
            from generate_progress_months import populate_progress_months
            
            logger.info("Running post-simulation hook: Deliverable_Progress_Month")
            count = populate_progress_months(str(db_path))
            if count > 0:
                logger.info(f"Post-simulation hook: generated {count} progress month records")
            elif count == 0:
                logger.warning("Post-simulation hook: no progress month records generated")
            else:
                logger.error("Post-simulation hook: progress month generation failed")
        except ImportError:
            logger.warning(
                "Post-simulation hook: generate_progress_months module not found. "
                "Run 'python generate_progress_months.py' manually."
            )
        except Exception as e:
            logger.error(f"Post-simulation hook (progress months) error: {e}")


def run_simulation_from_config_dir(sim_config_dir: Union[str, Path],
                                   db_config_path_or_content: Union[str, Path],
                                   db_path: Union[str, Path]) -> Dict[str, Dict[str, Any]]:
    """
    Run simulations for all configuration files in a directory
    
    Args:
        sim_config_dir: Directory containing simulation configuration files
        db_config_path_or_content: Path to the database configuration file or YAML content string.
        db_path: Path to the SQLite database
        
    Returns:
        Dictionary mapping configuration names to simulation results
    """
    if isinstance(sim_config_dir, str):
        sim_config_dir = Path(sim_config_dir)
        
    results = {}
    
    # Find all YAML files in the directory
    for config_file in sim_config_dir.glob("*.yaml"):
        config_name = config_file.stem
        logger.info(f"Running simulation for configuration: {config_name}")
        
        try:
            # Pass db_config_path_or_content to run_simulation
            sim_results = run_simulation(config_file, db_config_path_or_content, db_path)
            results[config_name] = sim_results
        except Exception as e:
            logger.error(f"Error running simulation for {config_name}: {e}")
            results[config_name] = {"error": str(e)}
    
    return results 
