"""
Entity management for DB Simulator.

This module handles entity creation and management for the simulation.
"""

import logging
import random
from datetime import timedelta
from typing import Dict, List, Tuple, Any, Optional
import dataclasses
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...config_parser import SimulationConfig, DatabaseConfig
from ...config_parser import Entity as DbEntity
from ...distributions import generate_from_distribution
from ...generator.data.attribute_generator import generate_attribute_value
from ...generator.data.type_processor import process_value_for_type
from ..utils.column_resolver import ColumnResolver

logger = logging.getLogger(__name__)

class EntityManager:
    """
    Manages entities for the event-based simulation.
    
    Handles entity creation, event creation, and relationship management.
    """
    
    def __init__(self, env, engine, db_path, config, db_config, event_tracker):
        """
        Initialize the entity manager
        
        Args:
            env: SimPy environment
            engine: SQLAlchemy engine
            db_path: Path to the SQLite database
            config: Simulation configuration
            db_config: Database configuration
            event_tracker: Event tracker instance
        """
        self.env = env
        self.engine = engine
        self.db_path = db_path
        self.config = config
        self.db_config = db_config
        self.event_tracker = event_tracker
        
        # Initialize column resolver for strict column type resolution
        if not db_config:
            raise ValueError("db_config is required for EntityManager - cannot use hardcoded column names")
        self.column_resolver = ColumnResolver(db_config)
        
        # Dictionary to track the current event type for each entity
        self.entity_current_event_types = {}
        
        # Counter for entities
        self.entity_count = 0
        
        # Precompute attributes that will be assigned by flows, per entity table
        self._assigned_attrs_by_entity = self._compute_assigned_attributes_by_entity()

    def _compute_assigned_attributes_by_entity(self) -> Dict[str, set]:
        """
        Analyze the simulation config to determine which entity attributes
        will be assigned by Assign steps in any flow. Returns a mapping of
        entity table name -> set of attribute names.
        """
        result: Dict[str, set] = {}
        
        event_sim = getattr(self.config, 'event_simulation', None)
        if not event_sim or not event_sim.event_flows:
            return result
            
        flows = event_sim.event_flows.flows if hasattr(event_sim.event_flows, 'flows') else event_sim.event_flows
        if not flows:
            return result
            
        # Map flow -> entity tables via Create steps
        flow_entities: Dict[str, set] = {}
        for flow in flows:
            ents = set()
            for step in flow.steps:
                if getattr(step, 'step_type', None) == 'create' and step.create_config and step.create_config.entity_table:
                    ents.add(step.create_config.entity_table)
            flow_entities[flow.flow_id] = ents
            
        # Collect assigned attribute names per entity across flows
        for flow in flows:
            target_entities = flow_entities.get(flow.flow_id, set())
            if not target_entities:
                continue
            for step in flow.steps:
                if getattr(step, 'step_type', None) == 'assign' and step.assign_config:
                    for assignment in step.assign_config.assignments or []:
                        attr_name = getattr(assignment, 'attribute_name', None)
                        if not attr_name:
                            continue
                        for ent in target_entities:
                            result.setdefault(ent, set()).add(attr_name)
                            
        return result
    
    def update_entity_attribute_column(self, entity_id: int, entity_table: str, 
                                     attribute_name: str, value) -> bool:
        """
        Update a specific attribute column in the entity table.
        
        Args:
            entity_id: ID of the entity to update
            entity_table: Name of the entity table
            attribute_name: Name of the attribute column to update
            value: Value to set (string, int, or float)
            
        Returns:
            True if update was successful, False otherwise
        """
        try:
            with Session(self.engine) as session:
                # Use parameterized query to prevent SQL injection
                # Get primary key column using column resolver
                pk_column = self.column_resolver.get_primary_key(entity_table)
                sql_query = text(f'UPDATE "{entity_table}" SET "{attribute_name}" = :value WHERE "{pk_column}" = :entity_id')
                
                result = session.execute(sql_query, {"value": value, "entity_id": entity_id})
                
                if result.rowcount > 0:
                    session.commit()
                    logger.debug(f"Updated {entity_table}.{attribute_name} = {value} for entity {entity_id}")
                    return True
                else:
                    logger.warning(f"No rows updated for entity {entity_id} in table {entity_table}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error updating attribute column {entity_table}.{attribute_name} for entity {entity_id}: {e}")
            return False
    
    def update_entity_attributes_batch(self, entity_id: int, entity_table: str, 
                                     attributes: Dict[str, Any]) -> bool:
        """
        Update multiple attribute columns for an entity in a single transaction.
        
        Args:
            entity_id: ID of the entity to update
            entity_table: Name of the entity table
            attributes: Dictionary of attribute_name -> value pairs
            
        Returns:
            True if all updates were successful, False otherwise
        """
        if not attributes:
            return True
        
        try:
            pk_column = self.column_resolver.get_primary_key(entity_table)
            with Session(self.engine) as session:
                # Build dynamic SET clause
                set_clauses = []
                params = {pk_column: entity_id}
                
                for attr_name, attr_value in attributes.items():
                    set_clauses.append(f'"{attr_name}" = :{attr_name}')
                    params[attr_name] = attr_value
                
                set_clause = ", ".join(set_clauses)
                sql_query = text(f'UPDATE "{entity_table}" SET {set_clause} WHERE "{pk_column}" = :{pk_column}')
                
                result = session.execute(sql_query, params)
                
                if result.rowcount > 0:
                    session.commit()
                    logger.debug(f"Batch updated {len(attributes)} attributes for entity {entity_id} in {entity_table}")
                    return True
                else:
                    logger.warning(f"No rows updated for entity {entity_id} in table {entity_table}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error batch updating attributes for entity {entity_id} in {entity_table}: {e}")
            return False
    
    def get_entity_config(self, entity_name: str) -> Optional[DbEntity]:
        """Find entity configuration by name."""
        if not self.db_config:
            return None
        for entity in self.db_config.entities:
            if entity.name == entity_name:
                return entity
        return None
    
    def get_table_by_type(self, table_type: str) -> Optional[str]:
        """Find a table with the specified type in the database configuration."""
        if not self.db_config:
            return None
        
        for entity in self.db_config.entities:
            if entity.type == table_type:
                return entity.name
                
        return None
    
    def get_table_names(self) -> Tuple[Optional[str], Optional[str]]:
        """Get entity and resource table names from config or db config."""
        event_sim = getattr(self.config, 'event_simulation', None)
        if not event_sim:
            return None, None

        if event_sim.table_specification:
            return event_sim.table_specification.entity_table, event_sim.table_specification.resource_table

        return self.get_table_by_type('entity'), self.get_table_by_type('resource')

    def create_entity(self, session, entity_table: str, initial_data: Optional[Dict[str, Any]] = None) -> int:
        """
        Create a new entity in the database, populating attributes based on generators.
        
        Args:
            session: SQLAlchemy session
            entity_table: Name of the entity table
            initial_data: Optional dictionary of attributes to set explicitly (overrides generators)
            
        Returns:
            ID of the created entity or None on error
        """
        try:
            entity_config = self.get_entity_config(entity_table)
            if not entity_config:
                logger.error(f"Database configuration not found for entity: {entity_table}")
                return None

            pk_column = self.column_resolver.get_primary_key(entity_table)
            
            # Check if PK has a custom generator
            pk_attr = next((attr for attr in entity_config.attributes if attr.is_primary_key), None)
            generated_pk = None
            
            if pk_attr and pk_attr.generator:
                # PK has a custom generator (e.g., faker uuid) - generate value
                gen_dict = dataclasses.asdict(pk_attr.generator) if pk_attr.generator else None
                attr_config_dict = {
                    'name': pk_attr.name,
                    'generator': gen_dict
                }
                
                # For template generators, we need the next sequence number to support {id}
                row_index = 0
                if getattr(pk_attr.generator, 'type', None) == 'template':
                    try:
                        # Use count as a proxy for the next row index (0-based)
                        # The template generator will add 1 to this for the {id} variable
                        count_result = session.execute(text(f'SELECT COUNT(*) FROM "{entity_table}"')).scalar()
                        row_index = int(count_result) if count_result is not None else 0
                    except Exception as e:
                        logger.warning(f"Could not determine row count for {entity_table}: {e}")
                
                generated_pk = generate_attribute_value(attr_config_dict, row_index)
                generated_pk = process_value_for_type(generated_pk, pk_attr.type)
                logger.debug(f"Generated custom PK value for {pk_attr.name}: {generated_pk}")
            
            row_data = {}
            
            # Include generated PK if using custom generator
            if generated_pk is not None:
                row_data[pk_column] = generated_pk
            
            # Apply initial data if provided
            if initial_data:
                for key, value in initial_data.items():
                    row_data[key] = value
            
            # Generate values for other attributes
            for attr in entity_config.attributes:
                if attr.is_primary_key:
                    continue  # Already handled above
                
                # Skip if already populated by initial_data
                if attr.name in row_data:
                    continue
                
                # Handle foreign key generator specifically
                if attr.generator and attr.generator.type == "foreign_key":
                    if not attr.ref:
                        logger.error(f"Foreign key attribute '{attr.name}' in table '{entity_table}' missing 'ref'. Assigning None.")
                        row_data[attr.name] = None
                    else:
                        ref_table, ref_column = attr.ref.split('.')
                        # Query the parent table for valid IDs
                        sql_query = text(f'SELECT "{ref_column}" FROM "{ref_table}"')
                        result = session.execute(sql_query).fetchall()
                        parent_ids = [id[0] for id in result]
                        
                        if not parent_ids:
                            logger.warning(f"No rows in parent table {ref_table}, assigning None to FK '{attr.name}' in '{entity_table}'")
                            row_data[attr.name] = None
                        else:
                            # Use user-defined distribution if present, else random
                            if attr.generator.formula:
                                # Use distribution formula for FK selection
                                from ...distributions import generate_from_distribution
                                try:
                                    # For FK, we need to map the generated value to parent_ids
                                    generated_value = generate_from_distribution(attr.generator.formula)
                                    if isinstance(generated_value, (int, float)):
                                        # If numeric, use as index (clamp to valid range)
                                        index = int(generated_value) % len(parent_ids)
                                        row_data[attr.name] = parent_ids[index]
                                    else:
                                        # If string/categorical, try to find in parent_ids, else use random
                                        row_data[attr.name] = random.choice(parent_ids)
                                except Exception as e:
                                    logger.warning(f"Error using formula for FK '{attr.name}': {e}. Using random assignment.")
                                    row_data[attr.name] = random.choice(parent_ids)
                            else:
                                # Uniform random assignment if no distribution is provided
                                row_data[attr.name] = random.choice(parent_ids)
                elif attr.generator:
                    # If this attribute is assigned later in flows for this entity,
                    # leave it NULL at creation time (no placeholder default).
                    assigned_for_entity = self._assigned_attrs_by_entity.get(entity_table, set())
                    if attr.name in assigned_for_entity:
                        continue
                    # Convert generator dataclass to dict for the utility function
                    gen_dict = dataclasses.asdict(attr.generator) if attr.generator else None
                    attr_config_dict = {
                        'name': attr.name,
                        'generator': gen_dict
                    }
                    # Pass 0 as row_index placeholder - most generators (faker, distribution) 
                    # don't use it. Template generators needing sequential IDs should be avoided
                    # for simulation-created entities or use the actual PK post-INSERT.
                    generated_value = generate_attribute_value(attr_config_dict, 0)
                    # Apply type-aware processing
                    row_data[attr.name] = process_value_for_type(generated_value, attr.type)
                else:
                    # Handle attributes without generators if necessary (e.g., default NULL or specific value)
                    # For now, let the DB handle defaults or NULL
                    pass
            
            # Check if the table has a datetime column and populate it automatically
            try:
                if entity_config:
                    for attr in entity_config.attributes:
                        if attr.type in ['datetime', 'timestamp'] and attr.name not in row_data:
                            # Calculate the current simulation date (date only — time-of-day
                            # is a continuous-time artifact with no business meaning)
                            creation_datetime = (self.config.start_date + timedelta(minutes=self.env.now)).date()
                            row_data[attr.name] = creation_datetime
                            logger.debug(f"Added {attr.name}={creation_datetime} for entity in {entity_table}")
            except Exception as e:
                logger.warning(f"Error setting datetime columns for {entity_table}: {e}")
            
            # Build INSERT statement dynamically (without PK - let database generate it)
            if row_data:
                columns = ", ".join([f'"{col}"' for col in row_data.keys()])
                placeholders = ", ".join([f":{col}" for col in row_data.keys()])
                sql_query = text(f'INSERT INTO "{entity_table}" ({columns}) VALUES ({placeholders})')
            else:
                # No data to insert - use default values
                sql_query = text(f'INSERT INTO "{entity_table}" DEFAULT VALUES')
            
            logger.debug(f"Creating entity in {entity_table} with data: {row_data}")
            result = session.execute(sql_query, row_data)
            
            # Return the appropriate primary key value
            if generated_pk is not None:
                # Used custom PK generator - return the generated value
                return generated_pk
            
            # Use lastrowid for auto-increment PKs
            generated_id = result.lastrowid
            
            if generated_id is None:
                logger.warning(
                    f"lastrowid returned None after INSERT into '{entity_table}'. "
                    f"This may indicate the table lacks an auto-increment primary key, "
                    f"or the database backend doesn't support lastrowid. "
                    f"Consider adding AUTOINCREMENT to the PK or implementing custom PK generation."
                )
            
            return generated_id
        except Exception as e:
            logger.error(f"Error creating entity in {entity_table}: {str(e)}", exc_info=True)
            return None

