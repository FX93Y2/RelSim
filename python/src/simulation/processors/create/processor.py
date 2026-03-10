"""
Create step processor for Arena-style entity creation.

This processor handles the creation of entities with specified arrival patterns
and routes them to their initial processing steps.
"""

import logging
import random
from datetime import timedelta
from typing import Optional, Generator, Dict, Any
from sqlalchemy import create_engine, insert, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from ..base import StepProcessor
from ...utils.column_resolver import ColumnResolver
from ..utils import extract_distribution_config, extract_distribution_config_with_time_unit
from ....distributions import generate_from_distribution
from ....utils.time_units import TimeUnitConverter

logger = logging.getLogger(__name__)


class CreateStepProcessor(StepProcessor):
    """
    Processor for Create step modules that generate entities dynamically.
    
    This processor implements Arena-style Create modules that:
    - Generate entities according to specified interarrival time distributions
    - Create entities in the specified database table
    - Route created entities to their initial processing step
    - Support entity limits and arrival patterns
    - Support triggered creation (sub-flows) from other entities
    """
    
    def __init__(self, env, engine, resource_manager, entity_manager, event_tracker, config, simulator=None):
        super().__init__(env, engine, resource_manager, entity_manager, event_tracker, config, simulator)
        # Callback for routing entities to initial steps (set by simulator)
        self.entity_router_callback = None
        
        # Initialize column resolver for strict column type resolution
        db_config = getattr(entity_manager, 'db_config', None)
        if not db_config:
            raise ValueError("db_config is required for CreateStepProcessor - cannot use hardcoded column names")
        self.column_resolver = ColumnResolver(db_config)
    
    def can_handle(self, step_type: str) -> bool:
        """Check if this processor can handle the given step type."""
        return step_type == "create"
    

    def validate_step(self, step: 'Step') -> bool:
        """Validate that the step configuration is correct for Create modules."""
        if not step.create_config:
            logger.error(f"Create step {step.step_id} missing create_config")
            return False
        
        config = step.create_config
        
        # Validate required fields
        if not config.entity_table:
            logger.error(f"Create step {step.step_id} missing entity_table")
            return False
            
        # interarrival_time is now optional (for triggered steps), but if present must be valid
        if config.interarrival_time:
            # Validate interarrival_time format (dict with 'distribution' OR 'formula', direct formula string, or numeric constant)
            if isinstance(config.interarrival_time, (str, int, float)):
                pass
            elif isinstance(config.interarrival_time, dict):
                if 'distribution' not in config.interarrival_time and 'formula' not in config.interarrival_time:
                    logger.error(f"Create step {step.step_id} interarrival_time dict must have 'distribution' or 'formula' key")
                    return False
            else:
                logger.error(f"Create step {step.step_id} interarrival_time must be string (formula), dict, or numeric constant")
                return False
            
        # Validate that the step has next_steps for routing entities
        if not step.next_steps:
            logger.error(f"Create step {step.step_id} missing next_steps for entity routing")
            return False
            
        return True
    
    def process(self, entity_id: int, step: 'Step', flow: 'EventFlow', 
                entity_table: str, event_flow: str, event_tracker=None) -> Generator:
        """
        Process the Create step.
        
        Modes:
        1. Standard (Source): entity_id is None. Schedules non-blocking arrivals based on interarrival_time.
        2. Triggered (Sub-flow): entity_id is NOT None. Spawns new entities immediately based on this trigger.
        
        Args:
            entity_id: Incoming entity ID (if triggered) or None (if source)
            step: Create step configuration
            flow: Event flow configuration
            entity_table: Not used (entity table comes from create_config)
            event_flow: Event flow label for tracking
            
        Yields:
            None
        """
        if not self.validate_step(step):
            logger.error(f"Invalid Create step configuration: {step.step_id}")
            return
            
        config = step.create_config
        
        if entity_id is not None:
             # --- Trigger Mode ---
            logger.info(f"Create module {step.step_id} triggered by entity {entity_id}")
            
            # Determine how many entities to create
            count = self._get_entities_per_arrival(config)
            logger.debug(f"Triggering generation of {count} entities in {config.entity_table}")
            
            # Context for new entities (linking to parent)
            parent_table = entity_table  # The table of the entity that triggered this
            
            initial_data = {}
            if parent_table:
                if parent_table == config.entity_table:
                    # Same-table create (e.g., Deliverable creates another Deliverable).
                    # The new entity should link to the GRANDPARENT (e.g., Project),
                    # not to the sibling entity that triggered this step.
                    # Look up the grandparent FK by reading the triggering entity's FK value.
                    fk_column, fk_value = self._resolve_grandparent_fk(
                        config.entity_table, entity_id, parent_table
                    )
                    if fk_column and fk_value is not None:
                        initial_data[fk_column] = fk_value
                        logger.debug(
                            f"Same-table create: resolved grandparent FK "
                            f"{fk_column}={fk_value} from entity {entity_id}"
                        )
                else:
                    # Normal parent-child create (e.g., Project creates Deliverable)
                    fk_column = self._find_parent_fk_column(config.entity_table, parent_table)
                    initial_data[fk_column] = entity_id
            
            # Create the batch immediately
            self._create_and_route_batch(count, step, flow, config, event_flow, initial_data)
            
            # The INCOMING entity (Parent) stops here *in this branch of execution*.
            # It is "consumed" by the Create step to produce children.
            return
        
        else:
            # --- Standard/Source Mode ---
            # Only start scheduling if interarrival_time is defined
            if not config.interarrival_time:
                # If no interarrival time and not triggered, this create step does nothing on its own.
                # (Active only when triggered)
                logger.info(f"Create module {step.step_id} has no interarrival_time; waiting for triggers.")
                return 

            logger.info(f"Starting Create module {step.step_id} for entity table '{config.entity_table}'")
            
            # Determine maximumentities to create
            max_entities = self._get_max_entities(config)
            logger.info(f"Create module {step.step_id} will generate up to {max_entities} entities")
            
            # Schedule the first arrival (non-blocking)
            self._schedule_next_arrival(step, flow, config, event_flow, 0, max_entities)
            
            # Return immediately - arrivals will continue independently
            return None
        
        yield  # Make this a generator (required by interface)
    
    def _schedule_next_arrival(self, step: 'Step', flow: 'EventFlow', config: 'CreateConfig', 
                              event_flow: str, entities_created: int, max_entities: int):
        """Schedule the next entity arrival as a separate non-blocking process."""
        # Generate interarrival time
        try:
            dist_config, time_unit = extract_distribution_config_with_time_unit(config.interarrival_time)
            interarrival_value = generate_from_distribution(dist_config)
            # Use specified time_unit or fall back to base_time_unit
            time_unit_to_use = time_unit if time_unit is not None else self.config.base_time_unit
            interarrival_minutes = TimeUnitConverter.to_minutes(interarrival_value, time_unit_to_use)
            
            # Schedule the arrival event
            self.env.process(self._entity_arrival_event(
                interarrival_minutes, step, flow, config, event_flow, entities_created, max_entities
            ))
            
        except Exception as e:
            logger.error(f"Error scheduling arrival for Create module {step.step_id}: {e}", exc_info=True)
    
    def _entity_arrival_event(self, delay: float, step: 'Step', flow: 'EventFlow', 
                             config: 'CreateConfig', event_flow: str, entities_created: int, max_entities: int):
        """Handle a single arrival event (possibly batch)."""
        try:
            # Wait for interarrival time
            yield self.env.timeout(delay)
            
            # Check if we should stop creating entities
            if max_entities != -1 and entities_created >= max_entities:
                logger.info(f"Create module {step.step_id} reached max entities ({max_entities})")
                return
            
            # Check termination conditions
            if self.simulator and self.simulator.termination_monitor:
                should_terminate, reason = self.simulator.termination_monitor._check_termination_conditions()
                if should_terminate:
                    logger.info(f"Create module {step.step_id} stopping - {reason}")
                    return
            
            # Determine how many entities to create in this arrival
            batch_size = self._get_entities_per_arrival(config)
            
            # Ensure we don't exceed max_entities
            if max_entities != -1:
                remaining_entities = max_entities - entities_created
                batch_size = min(batch_size, remaining_entities)
            
            # Create and route batch of entities
            successfully_created, _ = self._create_and_route_batch(batch_size, step, flow, config, event_flow)
            
            new_entities_created = entities_created + successfully_created
            
            if successfully_created > 0:
                if batch_size == 1:
                    logger.debug(f"Create module {step.step_id} created entity ({new_entities_created}/{max_entities if max_entities != -1 else '∞'})")
                else:
                    logger.debug(f"Create module {step.step_id} created {successfully_created} entities in batch ({new_entities_created}/{max_entities if max_entities != -1 else '∞'})")
            
            # Schedule next arrival if we haven't reached the limit
            if max_entities == -1 or new_entities_created < max_entities:
                self._schedule_next_arrival(step, flow, config, event_flow, new_entities_created, max_entities)
            else:
                logger.info(f"Create module {step.step_id} completed. Created {new_entities_created} entities")
                
        except Exception as e:
            logger.error(f"Error in arrival event for Create module {step.step_id}: {e}", exc_info=True)

    def _create_and_route_batch(self, count: int, step: 'Step', flow: 'EventFlow', 
                                config: 'CreateConfig', event_flow: str, 
                                initial_data: Optional[Dict[str, Any]] = None) -> (int, list):
        """
        Helper to create 'count' entities and route them to ALL next steps (Forking).
        
        Returns:
            (number_successfully_created, list_of_created_ids)
        """
        successfully_created = 0
        created_ids = []
        
        for i in range(count):
            # Pass initial_data (e.g. parent FKs) to creation
            created_entity_id = self._create_entity(config.entity_table, initial_data)
            
            if created_entity_id:
                # Increment entities processed counter for termination tracking
                if self.simulator:
                    self.simulator.initializer.entities_processed += 1
                
                # FORKING LOGIC: Route to ALL next steps
                for next_step_id in step.next_steps:
                    self._route_entity_to_next_step(created_entity_id, next_step_id, flow, 
                                                   config.entity_table, event_flow)
                
                successfully_created += 1
                created_ids.append(created_entity_id)
            else:
                logger.warning(f"Create module {step.step_id} failed to create entity")
        
        return successfully_created, created_ids

    def _get_entities_per_arrival(self, config: 'CreateConfig') -> int:
        """Get number of entities to create in this arrival."""
        if config.entities_per_arrival is None:
            return 1  # Default single entity
        
        # Support both integer and distribution
        if isinstance(config.entities_per_arrival, int):
            return config.entities_per_arrival
        else:
            # It's a distribution formula
            try:
                dist_config = extract_distribution_config(config.entities_per_arrival)
                return max(1, int(generate_from_distribution(dist_config)))
            except Exception as e:
                logger.warning(f"Error generating entities_per_arrival: {e}, using default 1")
                return 1
    
    def _get_max_entities(self, config: 'CreateConfig') -> int:
        """
        Determine maximum number of entities to create.
        
        Args:
            config: Create configuration
            
        Returns:
            Maximum entities to create, or -1 for unlimited
        """
        if config.max_entities is None or config.max_entities == 'n/a':
            return -1  # Unlimited - let simulation duration control termination
        
        return int(config.max_entities)
    
    def _create_entity(self, entity_table: str, initial_data: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """
        Create a new entity in the specified table.
        
        Args:
            entity_table: Name of the entity table
            initial_data: Optional data to override generation
            
        Returns:
            ID of created entity or None on failure
        """
        # Create a process-specific engine for this entity creation
        process_engine = create_engine(
            f"sqlite:///{self.entity_manager.db_path}?journal_mode=WAL",
            poolclass=NullPool,
            connect_args={"check_same_thread": False}
        )
        
        try:
            with Session(process_engine) as session:
                # Create entity using EntityManager, passing initial_data
                entity_id = self.entity_manager.create_entity(session, entity_table, initial_data)

                if entity_id:
                    session.commit()
                    
                    # Entity arrival time is now automatically tracked via created_at column
                    
                    # Update entity count
                    self.entity_manager.entity_count += 1
                    
                    return entity_id
                else:
                    logger.error(f"Failed to create entity in table {entity_table}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error creating entity in {entity_table}: {e}", exc_info=True)
            return None
        finally:
            process_engine.dispose()
    
    def _route_entity_to_next_step(self, entity_id: int, next_step_id: str, flow: 'EventFlow',
                                  entity_table: str, event_flow: str):
        """
        Route the created entity to its next processing step.
        """
        try:
            if self.entity_router_callback:
                # Use the simulator's callback for proper integration
                self.entity_router_callback(entity_id, next_step_id, flow, entity_table, event_flow)
            else:
                logger.warning(f"No entity router callback set. Entity {entity_id} cannot be routed to step {next_step_id}")
            
        except Exception as e:
            logger.error(f"Error routing entity {entity_id} to next step {next_step_id}: {e}", 
                        exc_info=True)
    
    def _find_parent_fk_column(self, child_table: str, parent_table: str) -> str:
        """
        Find the FK column in child_table that references parent_table.
        
        Args:
            child_table: Name of the child entity table
            parent_table: Name of the parent entity table
            
        Returns:
            Name of the FK column
            
        Raises:
            ValueError: If no FK column referencing parent_table is found
        """
        db_config = getattr(self.entity_manager, 'db_config', None)
        if not db_config:
            raise ValueError(
                f"Cannot find FK column: db_config is not available. "
                f"Child table '{child_table}' must have a foreign_key column referencing '{parent_table}'."
            )
        
        # Find the child entity configuration
        child_entity = None
        for entity in db_config.entities:
            if entity.name == child_table:
                child_entity = entity
                break
        
        if not child_entity:
            raise ValueError(
                f"Entity table '{child_table}' not found in database configuration."
            )
        
        # Search for an attribute with FK relationship to parent table
        for attr in child_entity.attributes:
            # Check 1: Generator-based FK (explicit foreign_key generator)
            if attr.generator and attr.generator.type == "foreign_key" and attr.ref:
                ref_table = attr.ref.split('.')[0]
                if ref_table == parent_table:
                    logger.debug(f"Found FK column '{attr.name}' in '{child_table}' referencing '{parent_table}' (generator-based)")
                    return attr.name
            
            # Check 2: Type-based FK (semantic types like entity_id, fk with ref)
            elif attr.ref and attr.type in ('entity_id', 'fk'):
                ref_table = attr.ref.split('.')[0]
                if ref_table == parent_table:
                    logger.debug(f"Found FK column '{attr.name}' in '{child_table}' referencing '{parent_table}' (type-based)")
                    return attr.name
        
        raise ValueError(
            f"No foreign key column found in '{child_table}' that references '{parent_table}'. "
            f"For triggered Create steps, the child entity table must have a column with "
            f"generator type='foreign_key' OR type in (entity_id, fk), plus ref='{parent_table}.<pk_column>'."
        )
    
    
    def _resolve_grandparent_fk(self, entity_table: str, entity_id: int, 
                                 parent_table: str) -> tuple:
        """
        Resolve the grandparent FK for same-table creates.
        
        When a Deliverable entity triggers creation of another Deliverable,
        we need to find the FK column that links to a DIFFERENT table (e.g., Project)
        and read its value from the triggering entity.
        
        Args:
            entity_table: The table being created (same as parent_table)
            entity_id: ID of the triggering (sibling) entity
            parent_table: The table of the triggering entity (same as entity_table)
            
        Returns:
            Tuple of (fk_column_name, fk_value) or (None, None) if not found
        """
        db_config = getattr(self.entity_manager, 'db_config', None)
        if not db_config:
            return (None, None)
        
        # Find the entity configuration
        entity_cfg = None
        for entity in db_config.entities:
            if entity.name == entity_table:
                entity_cfg = entity
                break
        
        if not entity_cfg:
            return (None, None)
        
        # Find the first FK column that references a DIFFERENT table
        fk_column = None
        for attr in entity_cfg.attributes:
            if attr.ref:
                ref_table = attr.ref.split('.')[0]
                if ref_table != entity_table:
                    # Found a FK to a different table (e.g., Deliverable.ProjectID → Project)
                    if (attr.generator and attr.generator.type == "foreign_key") or \
                       attr.type in ('entity_id', 'fk'):
                        fk_column = attr.name
                        break
        
        if not fk_column:
            logger.warning(
                f"Same-table create: no FK to a different table found in '{entity_table}'. "
                f"Cannot resolve grandparent FK."
            )
            return (None, None)
        
        # Read the FK value from the triggering entity
        process_engine = create_engine(
            f"sqlite:///{self.entity_manager.db_path}?journal_mode=WAL",
            poolclass=NullPool,
            connect_args={"check_same_thread": False}
        )
        
        try:
            # Find the PK column name
            pk_column = self.column_resolver.get_primary_key(entity_table)
            
            with process_engine.connect() as conn:
                result = conn.execute(
                    text(f"SELECT [{fk_column}] FROM [{entity_table}] WHERE [{pk_column}] = :eid"),
                    {"eid": entity_id}
                )
                row = result.fetchone()
                if row:
                    fk_value = row[0]
                    logger.debug(
                        f"Resolved grandparent FK: {fk_column}={fk_value} "
                        f"from {entity_table}[{pk_column}={entity_id}]"
                    )
                    return (fk_column, fk_value)
                else:
                    logger.warning(f"Entity {entity_id} not found in {entity_table}")
                    return (None, None)
        except Exception as e:
            logger.error(f"Error resolving grandparent FK: {e}", exc_info=True)
            return (None, None)
        finally:
            process_engine.dispose()


    def _find_step_by_id(self, step_id: str, flow: 'EventFlow') -> Optional['Step']:
        """Find a step by its ID within a flow."""
        for step in flow.steps:
            if step.step_id == step_id:
                return step
        return None
