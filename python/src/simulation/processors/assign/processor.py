"""
Assign step processor for Arena-style simulation steps.

This processor handles attribute assignment operations inspired by
Rockwell Arena's Assign module functionality.
"""

import logging
from typing import Any, Generator, Optional, TYPE_CHECKING

from ..base import StepProcessor
from .handlers.factory import AssignmentHandlerFactory

if TYPE_CHECKING:
    from ....config_parser.sim_parser import Step, EventFlow, AssignConfig
    from ...managers.entity_attribute_manager import EntityAttributeManager

logger = logging.getLogger(__name__)


class AssignStepProcessor(StepProcessor):
    """
    Processor for assign-type steps in the simulation flow.
    
    Handles Arena-style assignment operations including attribute assignments
    to entities during simulation execution.
    """
    
    def __init__(self, env, engine, resource_manager, entity_manager, event_tracker, config, simulator=None):
        """
        Initialize the assign step processor.
        
        Args:
            env: SimPy environment
            engine: SQLAlchemy engine
            resource_manager: Resource manager instance
            entity_manager: Entity manager instance
            event_tracker: Event tracker instance
            config: Simulation configuration
            simulator: Reference to the main simulator (for termination checking)
        """
        super().__init__(env, engine, resource_manager, entity_manager, event_tracker, config, simulator)
        
        # Assignment handler factory will be set during integration
        self.assignment_handler_factory: Optional[AssignmentHandlerFactory] = None
    
    def set_assignment_handler_factory(self, factory: AssignmentHandlerFactory):
        """
        Set the assignment handler factory.
        
        Args:
            factory: Assignment handler factory instance
        """
        self.assignment_handler_factory = factory
        self.logger.debug("Assignment handler factory set")
    
    def can_handle(self, step_type: str) -> bool:
        """Check if this processor can handle assign steps."""
        return step_type.lower() == "assign"
    
    def validate_step(self, step: 'Step') -> bool:
        """
        Validate that the step has proper assign configuration.
        
        Args:
            step: Step configuration to validate
            
        Returns:
            True if step is valid, False otherwise
        """
        if not super().validate_step(step):
            return False
        
        if step.step_type.lower() != "assign":
            self.logger.error(f"Invalid step type for AssignStepProcessor: {step.step_type}")
            return False
        
        if step.assign_config is None:
            self.logger.error(f"Assign step {step.step_id} missing assign_config")
            return False
        
        if not step.assign_config.assignments:
            self.logger.error(f"Assign step {step.step_id} has no assignments")
            return False
        
        # Validate each assignment operation
        if self.assignment_handler_factory:
            for assignment in step.assign_config.assignments:
                if not self.assignment_handler_factory.validate_assignment(assignment):
                    self.logger.error(f"Invalid assignment in step {step.step_id}: {assignment}")
                    return False
        
        return True
    
    def process(self, entity_id: int, step: 'Step', flow: 'EventFlow', 
                entity_table: str, event_flow: str, event_tracker=None) -> Generator[Any, None, Optional[str]]:
        """
        Process an assign step and execute all assignment operations.
        
        Args:
            entity_id: Entity ID
            step: Assign step configuration
            flow: Event flow configuration
            entity_table: Name of the entity table
            event_flow: Identifier/label of the event flow
            
        Yields:
            No SimPy events (assignment is instantaneous)
            
        Returns:
            Next step ID from next_steps list, or None if flow ends
        """
        if not self.validate_step(step):
            self.logger.error(f"Invalid assign step configuration for step {step.step_id}")
            return None
        
        if self.assignment_handler_factory is None:
            self.logger.error(f"No assignment handler factory available for step {step.step_id}")
            return None
        
        self.log_step_start(entity_id, step)
        
        assign_config: 'AssignConfig' = step.assign_config
        successful_assignments = 0
        total_assignments = len(assign_config.assignments)
        
        # Track successful attribute assignments for database update
        db_attributes = {}
        
        # Execute all assignment operations
        for assignment in assign_config.assignments:
            try:
                success = self.assignment_handler_factory.execute_assignment(entity_id, assignment, entity_table)
                if success:
                    successful_assignments += 1
                    # Track attribute assignments for database persistence
                    if assignment.attribute_name:
                        if assignment.assignment_type == 'attribute':
                            # For regular attribute assignments, use the direct value
                            db_attributes[assignment.attribute_name] = assignment.value
                        elif assignment.assignment_type == 'sql':
                            # For SQL SELECT assignments, get the value from entity_attribute_manager
                            if self.assignment_handler_factory and self.assignment_handler_factory.entity_attribute_manager:
                                value = self.assignment_handler_factory.entity_attribute_manager.get_attribute(entity_id, assignment.attribute_name)
                                if value is not None:
                                    db_attributes[assignment.attribute_name] = value
                                    self.logger.debug(f"Retrieved SQL result {assignment.attribute_name} = {value} for database persistence")
                                else:
                                    self.logger.warning(f"SQL assignment {assignment.attribute_name} returned None - not persisting to database")
                else:
                    self.logger.warning(f"Failed to execute assignment for entity {entity_id}: {assignment}")
            except Exception as e:
                self.logger.error(f"Error executing assignment for entity {entity_id}: {str(e)}", exc_info=True)
        
        # Update database columns with assigned attributes
        if db_attributes and self.entity_manager:
            try:
                # Check if the entity table has the attributes — if not,
                # resolve the parent entity and update that instead.
                actual_table = entity_table
                actual_entity_id = entity_id
                
                db_config = getattr(self.entity_manager, 'db_config', None)
                if db_config:
                    entity_cfg = next((e for e in db_config.entities if e.name == entity_table), None)
                    if entity_cfg:
                        entity_columns = {a.name for a in entity_cfg.attributes}
                        missing_attrs = set(db_attributes.keys()) - entity_columns
                        
                        if missing_attrs:
                            # Attribute not on current entity — look for a parent table
                            # that has these attributes (via FK)
                            for attr in entity_cfg.attributes:
                                if attr.ref and (
                                    (attr.generator and attr.generator.type == "foreign_key") or
                                    attr.type in ('entity_id', 'fk')
                                ):
                                    ref_table = attr.ref.split('.')[0]
                                    parent_cfg = next((e for e in db_config.entities if e.name == ref_table), None)
                                    if parent_cfg:
                                        parent_columns = {a.name for a in parent_cfg.attributes}
                                        if missing_attrs.issubset(parent_columns):
                                            # Read the parent FK value from the DB
                                            from sqlalchemy import text
                                            pk_col = next((a.name for a in entity_cfg.attributes if a.type == 'pk'), None)
                                            if pk_col:
                                                with self.engine.connect() as conn:
                                                    result = conn.execute(
                                                        text(f"SELECT [{attr.name}] FROM [{entity_table}] WHERE [{pk_col}] = :eid"),
                                                        {"eid": entity_id}
                                                    )
                                                    row = result.fetchone()
                                                    if row and row[0] is not None:
                                                        actual_table = ref_table
                                                        actual_entity_id = row[0]
                                                        self.logger.debug(
                                                            f"Cross-entity assign: updating {ref_table}[{actual_entity_id}] "
                                                            f"instead of {entity_table}[{entity_id}] for attrs {missing_attrs}"
                                                        )
                                                        break
                
                success = self.entity_manager.update_entity_attributes_batch(
                    actual_entity_id, actual_table, db_attributes
                )
                if success:
                    self.logger.debug(f"Persisted {len(db_attributes)} attributes to database for entity {actual_entity_id} in {actual_table}")
                else:
                    self.logger.warning(f"Failed to persist attributes to database for entity {actual_entity_id} in {actual_table}")
            except Exception as e:
                self.logger.error(f"Error persisting attributes to database for entity {entity_id}: {str(e)}", exc_info=True)
        
        # Log results
        if successful_assignments == total_assignments:
            self.logger.debug(f"Successfully executed all {total_assignments} assignments for entity {entity_id} in step {step.step_id}")
        elif successful_assignments > 0:
            self.logger.warning(f"Executed {successful_assignments}/{total_assignments} assignments for entity {entity_id} in step {step.step_id}")
        else:
            self.logger.error(f"Failed to execute any assignments for entity {entity_id} in step {step.step_id}")
        
        # Determine next step
        next_step_id = self._determine_next_step(step)
        
        self.log_step_end(entity_id, step, next_step_id)
        
        # Assignment processing is instantaneous - yield and return
        yield self.env.timeout(0)  # Instantaneous event
        return next_step_id
    
    def _determine_next_step(self, step: 'Step') -> Optional[str]:
        """
        Determine the next step ID based on step configuration.
        
        Args:
            step: Current step configuration
            
        Returns:
            Next step ID or None if flow ends
        """
        if not step.next_steps:
            return None
        
        # For assign steps, typically only one next step
        # (unlike decide steps which have conditional routing)
        return step.next_steps[0]
    
    def get_assignment_statistics(self) -> dict:
        """
        Get statistics about assignment operations.
        
        Returns:
            Dictionary with assignment statistics
        """
        if self.assignment_handler_factory is None:
            return {"error": "No assignment handler factory available"}
        
        return self.assignment_handler_factory.get_statistics()
    
    def get_supported_assignment_types(self) -> list:
        """
        Get list of supported assignment types.
        
        Returns:
            List of supported assignment type strings
        """
        if self.assignment_handler_factory is None:
            return []
        
        return self.assignment_handler_factory.get_supported_assignment_types()
    
    def get_arena_compatibility_status(self) -> dict:
        """
        Get Arena compatibility status for different assignment types.
        
        Returns:
            Dictionary mapping Arena features to support status
        """
        return {
            "Attribute assignments": "Fully supported",
            "Variable assignments": "Not implemented (future feature)",
            "Variable Array assignments": "Not implemented (future feature)",
            "Entity system attributes": "Not implemented (future feature)"
        }
