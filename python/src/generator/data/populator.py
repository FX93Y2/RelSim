"""
Database table population with synthetic data.

This module handles the population of database tables
with synthetic data based on entity configurations.
"""

import logging
import dataclasses
from typing import List, Any

from ...config_parser import DatabaseConfig, Entity, Attribute
from .attribute_generator import generate_attribute_value
from .type_processor import process_value_for_type

logger = logging.getLogger(__name__)


class DataPopulator:
    """Handles population of database tables with synthetic data."""
    
    def __init__(self):
        """Initialize the data populator."""
        self.pending_formulas = {}  # Store formula attributes for post-simulation resolution
    
    def populate_tables(self, models: dict, config: DatabaseConfig, session, 
                       flow_assigned_attributes: dict,
                       dynamic_entity_tables: List[str] = None,
                       project_dir: str = None):
        """
        Populate tables with data based on configuration
        
        Args:
            models: Dictionary of SQLAlchemy model classes
            config: Database configuration
            session: SQLAlchemy session
            dynamic_entity_tables: List of tables to skip during population
            flow_assigned_attributes: Map of entity_table -> set(attribute_names) that will be assigned in flows
            project_dir: Project root directory (for resolving script paths)
        """
        self.models = models
        self.session = session
        self.config = config
        self.dynamic_entity_tables = dynamic_entity_tables or []
        self.project_dir = project_dir
        # Map of entity_table -> set(attribute_names) that will be assigned in flows
        self.flow_assigned_attributes = flow_assigned_attributes
        
        # Sort entities to handle dependencies
        from ..schema import DependencySorter
        dependency_sorter = DependencySorter()
        sorted_entities = dependency_sorter.sort_entities_by_dependencies(config)
        
        # Populate all tables in sorted order
        for entity in sorted_entities:
            # Skip dynamic entity/event tables
            if entity.name in self.dynamic_entity_tables:
                continue
            self._populate_entity(entity)
    
    def _populate_entity(self, entity: Entity):
        """
        Populate table with data based on entity configuration
        
        Args:
            entity: Entity configuration
        """
        # Check for entity-level script generator — delegate entirely
        if entity.generator and entity.generator.type == 'script':
            self._execute_script_generator(entity)
            return

        model_class = self.models[entity.name]
        
        # Determine number of rows to generate
        num_rows = self._get_num_rows(entity)
        
        logger.info(f"Generating {num_rows} rows for table {entity.name}")
        
        # Collect formula attributes for post-simulation resolution
        formula_attrs = []
        for attr in entity.attributes:
            if attr.generator and getattr(attr.generator, "type", None) == "formula":
                formula_attrs.append(attr)
        
        # Store formula attributes if any exist
        if formula_attrs:
            self.pending_formulas[entity.name] = formula_attrs
            logger.info(f"Found {len(formula_attrs)} formula attributes in table {entity.name} for post-simulation resolution")
        
        # Pre-process one_to_one attributes to create shuffled ID decks
        one_to_one_decks = {}
        for attr in entity.attributes:
            if attr.generator and getattr(attr.generator, "type", None) == "foreign_key":
                subtype = getattr(attr.generator, "subtype", "many_to_one")
                if subtype == "one_to_one" and attr.ref:
                    ref_table, ref_column = attr.ref.split('.')
                    parent_model = self.models[ref_table]
                    # Fetch all parent IDs
                    parent_ids = self.session.query(getattr(parent_model, ref_column)).all()
                    parent_ids = [pid[0] for pid in parent_ids]
                    
                    if not parent_ids:
                        logger.warning(f"No parent rows found for 1:1 FK '{attr.name}' in '{entity.name}'")
                        one_to_one_decks[attr.name] = []
                    else:
                        import random
                        # Create a copy and shuffle it
                        deck = list(parent_ids)
                        random.shuffle(deck)
                        one_to_one_decks[attr.name] = deck
                        logger.info(f"Prepared 1:1 deck for {attr.name}: {len(deck)} unique IDs")

        # Generate rows
        for i in range(num_rows):
            row_data = {}
            
            # Generate data for each attribute
            for attr in entity.attributes:
                # Handle primary key - use generator if present, otherwise skip for auto-increment
                if attr.is_primary_key:
                    if attr.generator:
                        # PK has a custom generator (e.g., faker uuid)
                        row_data[attr.name] = self._generate_attribute_value(attr, i)
                        logger.debug(f"Generated PK value for {attr.name} using {attr.generator.type} generator")
                    # else: skip - let database handle auto-increment
                    continue

                # Check for formula type generators - skip during initial population
                if attr.generator and getattr(attr.generator, "type", None) == "formula":
                    logger.debug(f"Skipping formula attribute '{attr.name}' in table '{entity.name}' for post-simulation resolution")
                    continue

                # Handle new "foreign_key" generator type
                if attr.generator and getattr(attr.generator, "type", None) == "foreign_key":
                    subtype = getattr(attr.generator, "subtype", "many_to_one")
                    
                    if subtype == "one_to_one":
                        # Use the pre-shuffled deck
                        deck = one_to_one_decks.get(attr.name, [])
                        if deck:
                            row_data[attr.name] = deck.pop()
                        else:
                            logger.warning(f"Ran out of unique IDs for 1:1 FK '{attr.name}' in '{entity.name}' (Row {i+1}). Setting to None.")
                            row_data[attr.name] = None
                    else:
                        # Standard Many-to-One logic (formerly called One-to-Many)
                        # We accept "one_to_many" as a legacy alias for "many_to_one"
                        if subtype == "one_to_many":
                             logger.debug(f"Attribute '{attr.name}' uses legacy subtype 'one_to_many'. Treating as 'many_to_one'.")

                        # Get parent table and column
                        if not attr.ref:
                            logger.error(f"Foreign key attribute '{attr.name}' in table '{entity.name}' missing 'ref'. Assigning None.")
                            row_data[attr.name] = None
                        else:
                            ref_table, ref_column = attr.ref.split('.')
                            parent_model = self.models[ref_table]
                            parent_ids = self.session.query(getattr(parent_model, ref_column)).all()
                            parent_ids = [id[0] for id in parent_ids]
                            
                            if not parent_ids:
                                logger.warning(f"No rows in parent table {ref_table}, assigning None to FK '{attr.name}' in '{entity.name}'")
                                row_data[attr.name] = None
                            else:
                                # Use ForeignKeyResolver for proper formula-based selection
                                from .foreign_key import ForeignKeyResolver
                                fk_resolver = ForeignKeyResolver()
                                formula = getattr(attr.generator, 'formula', None)
                                row_data[attr.name] = fk_resolver.select_parent_id(parent_ids, formula)
                # Generate data based on other generator configuration
                elif attr.generator:
                    # If this attribute is assigned by any Assign step in flows,
                    # leave it NULL initially (no placeholder), so simulation can set it.
                    assigned_for_entity = self.flow_assigned_attributes.get(entity.name, set())
                    if attr.name in assigned_for_entity:
                        row_data[attr.name] = None
                    else:
                        row_data[attr.name] = self._generate_attribute_value(attr, i)
                # Handle foreign keys without generator
                elif attr.is_foreign_key:
                    logger.error(f"Missing generator for foreign key '{attr.name}' in table '{entity.name}'. Assigning None.")
                    row_data[attr.name] = None
                # Default value for other attributes without generator - Set to NULL for manual/SQL population
                else:
                    logger.debug(f"No generator for attribute '{attr.name}' in table '{entity.name}'. Setting to NULL for manual population.")
                    row_data[attr.name] = None
            
            # Create and add row
            # Ensure row_data doesn't contain keys not present in the model if assigning None to FKs caused issues
            valid_keys = {col.name for col in model_class.__table__.columns}
            filtered_row_data = {k: v for k, v in row_data.items() if k in valid_keys}
            
            try:
                 row = model_class(**filtered_row_data)
                 self.session.add(row)
            except Exception as e:
                 logger.error(f"Error creating row for {entity.name} with data {filtered_row_data}: {e}")

            self.session.add(row)
        
        # Commit after each table to make IDs available for foreign keys
        self.session.commit()
    
    def _get_num_rows(self, entity: Entity) -> int:
        """
        Determine number of rows to generate for an entity
        
        Args:
            entity: Entity configuration
            
        Returns:
            Number of rows to generate
        """
        # Handle fixed number of rows
        if isinstance(entity.rows, int):
            return entity.rows
        
        # Handle 'n/a' for event/entity tables
        if entity.rows == 'n/a':
            # For event/entity tables, we'll generate rows based on relationships
            # But here we're just skipping them for now
            return 0
        
        # Handle 'script' — script generator controls row count
        if entity.rows == 'script':
            return 0
        
        # Default value if rows is not specified
        return 10
    
    def _generate_attribute_value(self, attr: Attribute, row_index: int) -> Any:
        """
        Generate value for an attribute using the utility function.
        
        Args:
            attr: Attribute configuration object
            row_index: Index of current row
            
        Returns:
            Generated value
        """
        # Convert Attribute object's generator to dictionary for the utility function
        attr_config_dict = {
            'name': attr.name,
            'generator': dataclasses.asdict(attr.generator) if attr.generator else None
            # Add other necessary fields from attr if needed by the utility function
        }
        
        # Note: Pass 0-based row_index to the utility function
        generated_value = generate_attribute_value(attr_config_dict, row_index)
        
        # Process the value based on the attribute's data type
        return process_value_for_type(generated_value, attr.type)
    
    def has_pending_formulas(self) -> bool:
        """
        Check if there are any formula attributes waiting for post-simulation resolution.
        
        Returns:
            True if there are pending formulas, False otherwise
        """
        return bool(self.pending_formulas)

    def _execute_script_generator(self, entity: Entity):
        """
        Execute a user-provided script to generate rows for this table.
        
        Args:
            entity: Entity config with entity.generator.type == 'script'
        """
        from .script_executor import ScriptExecutor
        executor = ScriptExecutor()
        row_count = executor.execute(
            entity=entity,
            session=self.session,
            models=self.models,
            config=self.config,
            project_dir=self.project_dir,
        )
        logger.info(f"Script generated {row_count} rows for table '{entity.name}'")
        
        # Commit after script execution to make rows available for subsequent tables
        self.session.commit()
