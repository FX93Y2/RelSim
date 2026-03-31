"""
Database generator using SQLAlchemy.
Builds tables/relationships from config and fills them with synthetic data.
"""

import os
import logging
from typing import Optional, List
from pathlib import Path
from datetime import datetime

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from ..config_parser import DatabaseConfig, SimulationConfig
from ..utils.file_operations import safe_delete_sqlite_file, ensure_database_closed

from .schema import TableBuilder, DependencySorter
from .data import DataPopulator
from .simulation import SimulationAttributeAnalyzer

logger = logging.getLogger(__name__)


class DatabaseGenerator:
    def __init__(self, config: DatabaseConfig, output_dir: str = "output",
                 dynamic_entity_tables: Optional[List[str]] = None,
                 sim_config: Optional[SimulationConfig] = None,
                 project_dir: Optional[str] = None):
        """Initialize generator with configs and destination."""
        self.config = config
        self.sim_config = sim_config
        self.output_dir = output_dir
        self.project_dir = project_dir
        self.engine = None
        self.session = None
        self.dynamic_entity_tables = dynamic_entity_tables or []
        
        # Initialize components
        self.simulation_analyzer = SimulationAttributeAnalyzer(sim_config, config)
        self.table_builder = TableBuilder()
        self.data_populator = DataPopulator()
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
    
    def generate(self, db_name: Optional[str] = None) -> str:
        """Create database file and populate it."""
        # Pick a name if not provided
        if not db_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            db_name = f"generated_db_{timestamp}"
        
        # Ensure output directory exists
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            logger.info(f"Ensured output directory exists: {self.output_dir}")
            
            # Check if directory is writable
            if not os.access(self.output_dir, os.W_OK):
                logger.warning(f"Output directory {self.output_dir} is not writable!")
        except Exception as e:
            logger.error(f"Error creating output directory {self.output_dir}: {e}")
            # Try to find an alternative directory
            alt_dir = os.path.abspath('.')
            logger.info(f"Falling back to current directory: {alt_dir}")
            self.output_dir = alt_dir
            os.makedirs(self.output_dir, exist_ok=True)
        
        # Build absolute db path
        if os.path.isabs(self.output_dir):
            db_path = os.path.join(self.output_dir, f"{db_name}.db")
        else:
            db_path = os.path.abspath(os.path.join(self.output_dir, f"{db_name}.db"))
        
        logger.info(f"Generating database at absolute path: {db_path}")
        
        # Start from a clean file
        if not safe_delete_sqlite_file(db_path):
            logger.warning(f"Could not delete existing database file, continuing anyway: {db_path}")
        
        # Create SQLAlchemy engine with specific flags for better reliability
        connection_string = f"sqlite:///{db_path}"
        self.engine = create_engine(connection_string, echo=False)
        
        # Analyze simulation config for flow-specific attributes
        flow_attributes = self.simulation_analyzer.analyze_simulation_attributes()
        # Attributes set during flows stay NULL at generation time
        entity_assigned_attrs = self.simulation_analyzer.get_entity_attribute_names_map(flow_attributes)
        
        # Create tables
        models = self.table_builder.create_tables(self.config, self.engine, flow_attributes)
        
        # Create session
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        
        # Populate tables with data
        self.data_populator.populate_tables(
            models,
            self.config,
            self.session,
            entity_assigned_attrs,
            self.dynamic_entity_tables,
            project_dir=self.project_dir,
        )
        
        # Commit and close session
        self.session.commit()
        self.session.close()
        
        # Dispose engine for safe file operations
        ensure_database_closed(self.engine)
        
        # Verify the database file exists and is not empty
        self._verify_database(db_path)
        
        return db_path
    
    def _verify_database(self, db_path: str):
        """Basic existence/table check for the generated DB."""
        if not os.path.exists(db_path):
            logger.error(f"Database file was not created at expected path: {db_path}")
            
            # Log directory contents for debugging
            try:
                logger.info(f"Contents of directory {self.output_dir}:")
                for f in os.listdir(self.output_dir):
                    logger.info(f"  - {f}")
            except Exception as e:
                logger.error(f"Error listing directory contents: {e}")
                
            # Try connecting to the database directly as a final check
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                conn.close()
                logger.info(f"Successfully connected to database despite file check failure")
            except Exception as e:
                logger.error(f"Failed to connect to database: {e}")
        else:
            size = os.path.getsize(db_path)
            logger.info(f"Database generated successfully at {db_path}, size: {size} bytes")
            
            if size == 0:
                logger.warning(f"Database file exists but is empty (0 bytes)")
            
            # Verify the database can be opened
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # Check for tables
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                logger.info(f"Database contains {len(tables)} tables: {[t[0] for t in tables]}")
                
                conn.close()
            except Exception as e:
                logger.error(f"Error verifying database: {e}")
    
    def print_database_stats(self):
        """Print statistics about the generated database"""
        inspector = inspect(self.engine)
        
        logger.info("Database Statistics:")
        
        for table_name in inspector.get_table_names():
            # Create a new connection for executing queries
            with self.engine.connect() as connection:
                # Count rows
                count_query = text(f'SELECT COUNT(*) FROM "{table_name}"')
                result = connection.execute(count_query).scalar()
                
                logger.info(f"  {table_name}: {result} rows")
                
                # For child tables with foreign keys, show distribution
                foreign_keys = inspector.get_foreign_keys(table_name)
                
                if foreign_keys:
                    for fk in foreign_keys:
                        ref_table = fk['referred_table']
                        ref_column = fk['referred_columns'][0]
                        constrained_column = fk['constrained_columns'][0]
                        
                        # Get distribution of children per parent
                        distribution_query = text(f"""
                        SELECT {constrained_column}, COUNT(*) 
                        FROM {table_name} 
                        GROUP BY {constrained_column}
                        """)
                        distribution = connection.execute(distribution_query).fetchall()
                        
                        # Calculate statistics
                        counts = [count for _, count in distribution]
                        if counts:
                            min_count = min(counts)
                            max_count = max(counts)
                            avg_count = sum(counts) / len(counts)
                            
                            logger.info(f"    Relationship with {ref_table}: Min={min_count}, Max={max_count}, Avg={avg_count:.2f}")
                        else:
                            logger.info(f"    No relationships with {ref_table}")
    
    def has_pending_formulas(self) -> bool:
        """
        Check if there are any formula attributes waiting for post-simulation resolution.
        If populate_tables() was never called (e.g. API split workflow), scan config directly.

        Returns:
            True if there are pending formulas, False otherwise
        """
        if not self.data_populator.has_pending_formulas():
            self._scan_formula_attributes()
        return self.data_populator.has_pending_formulas()

    def _scan_formula_attributes(self):
        """Scan db config for formula attributes without populating tables."""
        for entity in self.config.entities:
            formula_attrs = [
                attr for attr in entity.attributes
                if attr.generator and getattr(attr.generator, "type", None) == "formula"
            ]
            if formula_attrs:
                self.data_populator.pending_formulas[entity.name] = formula_attrs
                logger.info(f"Scanned {len(formula_attrs)} formula attributes in table {entity.name}")
    
    def resolve_formulas(self, db_path: str) -> bool:
        """
        Resolve formula-based attributes after simulation completion.
        
        Args:
            db_path: Path to the database file
            
        Returns:
            True if resolution was successful, False otherwise
        """
        if not self.has_pending_formulas():
            logger.debug("No pending formulas to resolve")
            return True
        
        logger.info("Resolving formula-based attributes after simulation")
        
        try:
            # Create engine for the database
            connection_string = f"sqlite:///{db_path}"
            formula_engine = create_engine(connection_string, echo=False)
            
            # Import and use FormulaResolver
            from .data.formula import FormulaResolver
            resolver = FormulaResolver(formula_engine)
            
            # Resolve all pending formulas
            success = resolver.resolve_all(self.data_populator.pending_formulas)
            
            # Close the engine
            ensure_database_closed(formula_engine)
            
            if success:
                logger.info("Formula resolution completed successfully")
            else:
                logger.error("Formula resolution failed")
            
            return success
            
        except Exception as e:
            logger.error(f"Error during formula resolution: {e}")
            return False
