"""
Event step processor for handling event-based simulation steps.

This processor handles event steps that involve resource allocation,
duration processing, and event creation in the database.
"""

import logging
import random
from datetime import timedelta
from typing import Any, Generator, Optional

from ..base import StepProcessor
from ..utils import extract_distribution_config, extract_distribution_config_with_time_unit
from ....distributions import generate_from_distribution
from ....utils.time_units import TimeUnitConverter

logger = logging.getLogger(__name__)


class EventStepProcessor(StepProcessor):
    """
    Processor for event-type steps in the simulation flow.

    Handles resource allocation, event duration, database event creation,
    and resource release upon completion.
    """

    def __init__(self, env, engine, resource_manager, entity_manager, event_tracker, config, simulator=None, queue_manager=None):
        """Initialize EventStepProcessor with ColumnResolver and QueueManager support."""
        super().__init__(env, engine, resource_manager, entity_manager, event_tracker, config, simulator)

        # Store queue manager reference for queue-aware resource allocation
        self.queue_manager = queue_manager
        # Synthetic ID generator for runs without an event table
        self.synthetic_event_counter = 0

        # Database config (set via set_db_config)
        self.db_config = None

    def set_db_config(self, db_config):
        """Set the database configuration."""
        self.db_config = db_config
    
    def can_handle(self, step_type: str) -> bool:
        """Check if this processor can handle event steps."""
        return step_type == "event"
    
    def validate_step(self, step: 'Step') -> bool:
        """Validate that the step has proper event configuration."""
        if not super().validate_step(step):
            return False
        return (step.step_type == "event" and 
                step.event_config is not None)
    
    def process(self, entity_id: int, step: 'Step', flow: 'EventFlow', 
                entity_table: str, event_flow: str, event_tracker=None) -> Generator[Any, None, Optional[str]]:
        """
        Process an event step with resource allocation and duration.
        
        Args:
            entity_id: Entity ID
            step: Event step configuration
            flow: Event flow configuration
            entity_table: Name of the entity table
            event_flow: Identifier/label of the event flow
            
        Yields:
            SimPy events during processing
            
        Returns:
            Next step ID from the step configuration
        """
        # Use provided event_tracker or fall back to default
        active_event_tracker = event_tracker or self.event_tracker
        
        if not self.validate_step(step):
            self.logger.error(f"Invalid event step configuration for step {step.step_id}")
            return None
        
        self.log_step_start(entity_id, step)
        
        event_config = step.event_config
        event_flow_label = event_flow or getattr(flow, 'event_flow', None) or getattr(flow, 'flow_id', None)

        try:
            # Create event in database (or synthetic placeholder when event table is absent)
            event_id = self._create_event_for_step(
                None, entity_id, step, entity_table, event_flow_label
            )

            if event_id is None:
                self.logger.warning(
                    f"Falling back to synthetic event id for step {step.step_id} (entity {entity_id})"
                )
                event_id = self._next_synthetic_event_id(step)

            # Retrieve entity attributes for queue priority calculation (if needed)
            entity_attributes = {}

            # Determine if this step is part of a resource group
            current_group_id = step.group_id
            
            # Allocate resources if required
            if event_config.resource_requirements:
                requirements_list = self._convert_resource_requirements(
                    event_config.resource_requirements
                )

                try:
                    # Check if we can reuse group resources
                    group_resources = []
                    needs_new_allocation = True
                    
                    if current_group_id:
                        group_resources = self.resource_manager.get_group_resources(entity_id, current_group_id)


                        if group_resources:
                            # Filter group resources by step's requirements


                            matched_resources, unmet_requirements = self._filter_group_resources_by_requirements(
                                group_resources, requirements_list
                            )

                            
                            allocation_key = f"{event_flow_label}_{event_id}" if event_flow_label else str(event_id)
                            
                            if unmet_requirements:
                                # Partial match - allocate only what's missing
                                uses_queue = any(req.get('queue') for req in unmet_requirements)
                                if uses_queue and self.queue_manager:
                                    yield self.env.process(
                                        self.resource_manager.allocate_resources(
                                            event_id, unmet_requirements, event_flow_label,
                                            entity_id=entity_id,
                                            entity_table=entity_table,
                                            entity_attributes=entity_attributes,
                                            queue_manager=self.queue_manager
                                        )
                                    )
                                else:
                                    yield self.env.process(
                                        self.resource_manager.allocate_resources(event_id, unmet_requirements, event_flow_label)
                                    )
                                # Combine matched from group + newly allocated
                                newly_allocated = self.resource_manager.event_allocations.get(allocation_key, [])
                                combined = matched_resources + newly_allocated
                                self.resource_manager.event_allocations[allocation_key] = combined
                                # Add only NEW resources to group
                                if newly_allocated:
                                    self.resource_manager.add_to_group(entity_id, current_group_id, newly_allocated)


                            else:
                                # Full match from group - just use matched resources
                                self.resource_manager.event_allocations[allocation_key] = matched_resources


                            needs_new_allocation = False
                    
                    if needs_new_allocation:
                        # No group or empty group - full allocation needed
                        uses_queue = any(req.get('queue') for req in requirements_list)

                        if uses_queue and self.queue_manager:
                            yield self.env.process(
                                self.resource_manager.allocate_resources(
                                    event_id, requirements_list, event_flow_label,
                                    entity_id=entity_id,
                                    entity_table=entity_table,
                                    entity_attributes=entity_attributes,
                                    queue_manager=self.queue_manager
                                )
                            )
                        else:
                            yield self.env.process(
                                self.resource_manager.allocate_resources(event_id, requirements_list, event_flow_label)
                            )
                        
                        # Add newly allocated resources to group if group_id is set
                        if current_group_id:
                            allocation_key = f"{event_flow_label}_{event_id}" if event_flow_label else str(event_id)
                            allocated = self.resource_manager.event_allocations.get(allocation_key, [])
                            if allocated:
                                self.resource_manager.add_to_group(entity_id, current_group_id, allocated)

                    self.logger.debug(f"Resources allocated for event {event_id}")
                except Exception as e:
                    self.logger.warning(f"Resource allocation failed for event {event_id}: {e}")
                    return None
            
            # Process event duration
            duration_minutes = self._calculate_event_duration(event_config)
            start_time = self.env.now
            
            # Wait for the event duration
            yield self.env.timeout(duration_minutes)
            
            end_time = self.env.now
            
            # Record resource allocations in the tracker
            self._record_resource_allocations(
                event_id,
                start_time,
                end_time,
                event_flow_label,
                active_event_tracker,
                entity_id=entity_id,
                entity_table=entity_table,
                event_type=step.step_id,
                bridge_table=event_config.bridge_table
            )
            
            # Increment events processed counter for termination tracking
            if self.simulator:
                self.simulator.initializer.processed_events += 1
            
            # Record event processing
            self._record_event_processing(
                self.engine, event_flow_label, event_id, entity_id,
                start_time, end_time, duration_minutes, active_event_tracker,
                entity_table=entity_table
            )
            
            # Determine next step and its group_id
            next_step_id = step.next_steps[0] if step.next_steps else None
            next_group_id = self._get_step_group_id(next_step_id, flow) if next_step_id else None

                

            # Release resources - but skip if next step has same group_id
            if current_group_id and next_group_id == current_group_id:
                # Keep resources for next step in the same group


                # Clear event allocation without releasing resources
                allocation_key = f"{event_flow_label}_{event_id}" if event_flow_label else str(event_id)
                if allocation_key in self.resource_manager.event_allocations:
                    del self.resource_manager.event_allocations[allocation_key]
            elif current_group_id and next_group_id != current_group_id:
                # Exiting group - release all group resources
                self.resource_manager.release_group_resources(entity_id, current_group_id)
                # Clear event allocation as well
                allocation_key = f"{event_flow_label}_{event_id}" if event_flow_label else str(event_id)
                if allocation_key in self.resource_manager.event_allocations:
                    del self.resource_manager.event_allocations[allocation_key]
            else:
                # No group - standard release
                self.resource_manager.release_resources(event_id, event_flow_label)
            
            self.logger.debug(
                f"Processed event {event_id} (step {step.step_id}) for entity {entity_id} "
                f"in {duration_minutes/60:.2f} hours"
            )
            
        except Exception as e:
            self.logger.error(f"Error processing event step {step.step_id}: {str(e)}", exc_info=True)
            return None
        
        # Determine next step
        next_step_id = step.next_steps[0] if step.next_steps else None
        self.log_step_end(entity_id, step, next_step_id)
        return next_step_id
    
    def _create_event_for_step(self, session, entity_id: int, step: 'Step', 
                              entity_table: str, event_flow: Optional[str]) -> Optional[int]:
        """
        Create an event record in the database for this step.
        
        Args:
            session: Database session
            entity_id: Entity ID
            step: Step configuration
            entity_table: Name of entity table
            event_flow: Label of event flow
            
        Returns:
            Created event ID or None if failed
        """
        synthetic_id = self._next_synthetic_event_id(step)
        self.logger.debug(
            f"Using synthetic event id {synthetic_id} for step {step.step_id} (flow={event_flow})"
        )
        return synthetic_id
    
    def _get_step_group_id(self, step_id: str, flow) -> Optional[str]:
        """
        Look up a step's group_id from the flow.
        
        Args:
            step_id: Step ID to look up
            flow: Event flow containing the steps
            
        Returns:
            group_id if found, else None
        """
        if not flow or not hasattr(flow, 'steps'):
            return None
        for step in flow.steps:
            if step.step_id == step_id:
                return step.group_id
        return None
    
    def _filter_group_resources_by_requirements(self, group_resources: list, requirements: list) -> tuple:
        """
        Filter group resources to match step requirements.
        
        For each requirement, find matching resources from the group by type
        and randomly select the required count. Returns both matched resources
        and any requirements that couldn't be met from the group.
        
        Args:
            group_resources: List of Resource objects in the group
            requirements: List of requirement dicts with 'value' (type) and 'count'
            
        Returns:
            Tuple of (matched_resources, unmet_requirements):
            - matched_resources: List of Resource objects from group
            - unmet_requirements: List of requirement dicts that need new allocation
        """
        matched = []
        unmet = []
        available = list(group_resources)  # Copy to avoid modifying original
        
        for req in requirements:
            required_type = req.get('value', '')
            required_count = req.get('count', 1)
            
            # Find resources matching this type
            matching = [r for r in available if r.type == required_type]
            
            if len(matching) >= required_count:
                # Fully satisfied from group - randomly select required count
                selected = random.sample(matching, required_count)
                matched.extend(selected)
                # Remove selected from available pool
                for r in selected:
                    available.remove(r)
                self.logger.debug(f"Matched {required_count} '{required_type}' from group")
            elif len(matching) > 0:
                # Partially satisfied - take what we have, need more
                matched.extend(matching)
                for r in matching:
                    available.remove(r)
                # Need to allocate the remainder
                remaining_count = required_count - len(matching)
                unmet.append({**req, 'count': remaining_count})
                self.logger.debug(f"Partial match: got {len(matching)} '{required_type}' from group, need {remaining_count} more")
            else:
                # Not satisfied at all from group - need full allocation
                unmet.append(req)
                self.logger.debug(f"No '{required_type}' in group, need to allocate {required_count}")
        
        return matched, unmet

    def _convert_resource_requirements(self, requirements) -> list:
        """Convert resource requirements to the format expected by resource manager."""
        requirements_list = []
        for req in requirements:
            # Handle distribution formulas for count
            count_val = req.count
            if isinstance(count_val, str):
                try:
                    # Parse distribution config using the utility
                    # We reuse extract_distribution_config which is imported
                    dist_config = extract_distribution_config(count_val)
                    # Generate value
                    val = generate_from_distribution(dist_config)
                    # Convert to int, ensure valid count (at least 1 usually, but 0 might be valid contextually?)
                    # Generally resources required implies > 0, but 0 is safe to process (just no allocation)
                    count_val = max(0, int(round(val)))
                except Exception as e:
                    self.logger.warning(f"Error evaluating resource count formula '{req.count}': {e}. Defaulting to 1.")
                    count_val = 1

            req_dict = {
                'resource_table': req.resource_table,
                'value': req.value,
                'count': count_val
            }
            # Include queue reference if specified
            if hasattr(req, 'queue') and req.queue:
                req_dict['queue'] = req.queue
            requirements_list.append(req_dict)
        return requirements_list
    
    def _calculate_event_duration(self, event_config) -> float:
        """Calculate event duration in minutes from configuration."""
        try:
            # Extract the actual distribution config and time unit from duration field
            dist_config, time_unit = extract_distribution_config_with_time_unit(event_config.duration)
            duration_value = generate_from_distribution(dist_config)
            # Use specified time_unit or fall back to base_time_unit
            time_unit_to_use = time_unit if time_unit is not None else self.config.base_time_unit
            return TimeUnitConverter.to_minutes(duration_value, time_unit_to_use)
        except Exception as e:
            self.logger.warning(f"Error calculating event duration: {str(e)}, using default")
            return 60.0  # Default 1 hour
    
    def _record_event_processing(self, engine, event_flow: Optional[str], event_id: int, 
                                entity_id: int, start_time: float, end_time: float, 
                                duration_minutes: float, event_tracker=None, entity_table: str = None):
        """Record event processing in the event tracker."""
        try:
            # Use provided event_tracker or fall back to default
            active_event_tracker = event_tracker or self.event_tracker
            # Calculate datetime values
            start_datetime = None
            end_datetime = None
            
            # Try to get start_date from config if available
            if self.config and hasattr(self.config, 'start_date') and self.config.start_date:
                start_datetime = self.config.start_date + timedelta(minutes=start_time)
                end_datetime = self.config.start_date + timedelta(minutes=end_time)
            
            event_flow_label = self._get_event_flow_label(event_flow)

            # Record in event tracker if available
            if active_event_tracker:
                 active_event_tracker.record_event_processing(
                     event_flow=event_flow_label,
                     event_id=event_id,
                     entity_id=entity_id,
                     start_time=start_time,
                     end_time=end_time,
                     entity_table=entity_table
                 )
                    
        except Exception as e:
            self.logger.warning(f"Error recording event processing: {str(e)}")
    
    def _record_resource_allocations(self, event_id: int, start_time: float, end_time: float, event_flow: str,
                                     event_tracker=None, entity_id: Optional[int] = None, 
                                     entity_table: str = None, event_type: Optional[str] = None,
                                     bridge_table: Optional[str] = None):
        """Record resource allocations in the event tracker."""
        try:
            active_event_tracker = event_tracker or self.event_tracker
            # Use composite key to handle ID collisions between event tables
            allocation_key = f"{event_flow}_{event_id}" if event_flow else str(event_id)
            
            if active_event_tracker and allocation_key in self.resource_manager.event_allocations:
                
                # Check for bridge table generators
                extra_attributes = {}
                if bridge_table and self.db_config:
                    # Find bridge entity config
                    bridge_entity = next((e for e in self.db_config.entities if e.name == bridge_table), None)
                    if bridge_entity:
                        from ....generator.data.attribute_generator import generate_attribute_value
                        from ....generator.data.formula.evaluator import FormulaEvaluator
                        # We might need a session for formula evaluation if complex formulas are used
                        # For now, simple generation
                        
                        for attr in bridge_entity.attributes:
                            # Skip standard logging columns handled by tracker
                            if attr.name in ('id', 'event_id', 'start_date', 'end_date', 'event_type'):
                                continue
                            # Skip entity fk and resource fk (handled by tracker logic if named correctly)
                            if attr.type in ('entity_id', 'resource_id'):
                                continue
                            
                            # Handle FK with formula - generate value from the distribution
                            if attr.generator and attr.generator.type == 'foreign_key':
                                # Only skip FKs that don't have a formula - those are handled elsewhere
                                if not attr.generator.formula:
                                    continue
                                # FK with formula: look up actual parent PKs and select by position
                                try:
                                    if attr.ref:
                                        ref_table, ref_column = attr.ref.split('.')
                                        # Query the parent table for actual PK values
                                        from sqlalchemy import text
                                        from sqlalchemy.orm import sessionmaker
                                        Session = sessionmaker(bind=self.engine)
                                        with Session() as session:
                                            result = session.execute(text(f'SELECT "{ref_column}" FROM "{ref_table}"'))
                                            parent_ids = [row[0] for row in result.fetchall()]
                                        
                                        if parent_ids:
                                            # Use ForeignKeyResolver to select by position
                                            from ....generator.data.foreign_key import ForeignKeyResolver
                                            fk_resolver = ForeignKeyResolver()
                                            val = fk_resolver.select_parent_id(parent_ids, attr.generator.formula)
                                            extra_attributes[attr.name] = val
                                        else:
                                            self.logger.warning(f"No parent records found in {ref_table} for FK {attr.name}")
                                    else:
                                        self.logger.warning(f"FK {attr.name} has formula but no ref defined")
                                except Exception as e:
                                    self.logger.warning(f"Error generating FK {attr.name} from formula {attr.generator.formula}: {e}")
                                continue
                            
                            # Safest is to generate only if it has a generator
                            
                            if attr.generator:
                                try:
                                    # Convert to dict format expected by generator
                                    attr_dict = {
                                        'name': attr.name,
                                        'generator': {
                                            'type': attr.generator.type,
                                            'method': attr.generator.method,
                                            'template': attr.generator.template,
                                            'formula': attr.generator.formula,
                                            'expression': getattr(attr.generator, 'expression', None)
                                        }
                                    }
                                    # Use a dummy index 0 or event_id as seed proxy
                                    val = generate_attribute_value(attr_dict, event_id)
                                    # Apply type processing to respect integer/decimal constraints
                                    from ....generator.data.type_processor import process_value_for_type
                                    val = process_value_for_type(val, attr.type)
                                    extra_attributes[attr.name] = val
                                except Exception as e:
                                    self.logger.warning(f"Error generating attribute {attr.name} for bridge {bridge_table}: {e}")

                allocated_resources = self.resource_manager.event_allocations[allocation_key]
                for resource in allocated_resources:
                    # Record in the event tracker
                    active_event_tracker.record_resource_allocation(
                        event_flow=event_flow or self._get_event_flow_label(None),
                        event_id=event_id,
                        resource_table=resource.table,
                        resource_id=resource.id,
                        allocation_time=start_time,
                        release_time=end_time,
                        entity_id=entity_id,
                        entity_table=entity_table,
                        event_type=event_type,
                        target_bridge_table=bridge_table,
                        extra_attributes=extra_attributes
                    )
                self.logger.debug(f"Recorded {len(allocated_resources)} resource allocations for event {event_id}")
        except Exception as e:
            self.logger.warning(f"Error recording resource allocations for event {event_id}: {str(e)}")

    def _next_synthetic_event_id(self, step: 'Step') -> int:
        """Generate a synthetic event ID when no event table is available."""
        self.synthetic_event_counter += 1
        return self.synthetic_event_counter

    def _get_event_flow_label(self, event_flow: Optional[str]) -> str:
        """Provide a non-empty label for logging when no event flow is provided."""
        if event_flow:
            return event_flow
        try:
            fallback_entity_table = self.entity_manager.get_table_by_type('entity')
            return fallback_entity_table or 'event'
        except Exception:
            return 'event'
