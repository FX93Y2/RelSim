"""SimPy-based simulator that runs configured flows and resources."""

import logging
from typing import Dict, Any

from ...config_parser import SimulationConfig, DatabaseConfig
from .initialization import SimulatorInitializer, FlowEventTrackerSetup, ResourceInitializer
from .execution import FlowManager
from .lifecycle import TerminationMonitor, DatabaseCleanup, MetricsCollector

logger = logging.getLogger(__name__)


class EventSimulator:
    """
    SimPy simulator that runs flows, allocates resources, and gathers metrics.
    
    Delegates setup to initializer/tracker/resource helpers, executes via FlowManager,
    and wraps termination/metrics/cleanup.
    """

    def __init__(self, config: SimulationConfig, db_config: DatabaseConfig, db_path: str):
        """
        Wire up configs and build all subcomponents.
        
        Args:
            config: Parsed simulation config.
            db_config: Parsed database config.
            db_path: Path to the SQLite database.
        """
        self.config = config
        self.db_config = db_config
        self.db_path = db_path
        
        # Initialize core components using modular architecture
        self.initializer = SimulatorInitializer(config, db_config, db_path)
        self.tracker_setup = FlowEventTrackerSetup(db_path, config, db_config)
        self.cleanup_handler = DatabaseCleanup(db_path)
        
        # Components that will be initialized during setup
        self.flow_manager = None
        self.termination_monitor = None
        self.metrics_collector = None
        self.resource_initializer = None
        self.flow_event_trackers = None
        
        # Set up all components
        self._initialize_all_components()
    
    def _initialize_all_components(self):
        """Set up env, DB engine, managers, processors, trackers, and lifecycle hooks."""
        # Initialize core SimPy environment and database
        self.initializer.initialize_environment()
        self.initializer.initialize_database_engine()
        self.initializer.initialize_random_seed()
        self.initializer.initialize_termination_system()
        
        # Set up flow-specific event trackers
        self.flow_event_trackers = self.tracker_setup.initialize_flow_event_trackers()
        
        # Initialize managers with flow trackers
        self.initializer.initialize_managers(self.flow_event_trackers)
        
        # Initialize step processor factory with self reference
        self.initializer.initialize_step_processor_factory(self)
        
        # Initialize resource setup
        self.resource_initializer = ResourceInitializer(
            self.initializer.resource_manager, self.config
        )
        
        # Initialize execution components
        self.flow_manager = FlowManager(
            self.initializer.env, self.config, self.initializer.step_processor_factory,
            self.flow_event_trackers, self.initializer.entity_manager
        )
        
        # Initialize lifecycle components
        self.termination_monitor = TerminationMonitor(
            self.initializer.env, self.initializer, self
        )
        self.metrics_collector = MetricsCollector(
            self.config, self.initializer.env, self.initializer
        )
        
        logger.debug("All simulation components initialized successfully")
    
    def run(self) -> Dict[str, Any]:
        """
        Run the simulation and return final metrics/results.
        
        Returns:
            Dict with termination reason and collected metrics.
        """
        try:
            # Set random seed again to ensure consistency
            self.initializer.initialize_random_seed()
            
            # Setup resources using resource initializer
            self.resource_initializer.setup_resources()
            
            # Start entity generation processes using flow manager
            self.flow_manager.start_create_modules()
            
            # Start native periodic snapshots process
            try:
                from .lifecycle.snapshot_manager import SnapshotManager
                self.snapshot_manager = SnapshotManager(
                    self.initializer.env, 
                    self.initializer.engine, 
                    self.config
                )
                self.initializer.env.process(self.snapshot_manager.run_periodic_snapshots())
                logger.debug("Native SnapshotManager process started")
            except Exception as e:
                logger.warning(f"Failed to start SnapshotManager: {e}")
            
            # Log simulation start
            self.termination_monitor.log_simulation_start()
            
            # Start termination monitoring process and run until it finishes
            # This ensures the environment stops exactly when a termination
            # condition is met, rather than running until the event queue is empty.
            termination_event = self.termination_monitor.start_monitoring()
            
            # Run simulation until the termination monitor process exits
            self.initializer.env.run(until=termination_event)
            
            # Clean up any remaining allocated resources
            self._cleanup_remaining_resources()

            # NOTE: snapshot_manager.flush_to_database() is intentionally NOT
            # called here. It is invoked by runner.py AFTER post-processing
            # hooks (fix_billing_rates, calculate_financials) have populated
            # PlannedStartDate/EndDate and other derived fields. Flushing
            # here would snapshot NULL plan dates.

            logger.debug(f"Simulation completed. Processed {self.initializer.processed_events} events for {self.initializer.entity_manager.entity_count} entities")
            
            # Collect and return final results
            return self.metrics_collector.collect_final_results(
                self.termination_monitor.get_termination_reason()
            )
            
        finally:
            # ALWAYS clean up database connections to prevent EBUSY errors on Windows
            self._cleanup_database_connections()
    
    def _cleanup_remaining_resources(self):
        """Release any resources still allocated."""
        if hasattr(self.initializer.resource_manager, 'event_allocations'):
            remaining_allocations = list(self.initializer.resource_manager.event_allocations.keys())
            if remaining_allocations:
                logger.info(f"Cleaning up {len(remaining_allocations)} remaining resource allocations")
                for event_id in remaining_allocations:
                    try:
                        self.initializer.resource_manager.release_resources(event_id)
                    except Exception as e:
                        logger.debug(f"Error releasing resources for event {event_id}: {e}")
    
    def _cleanup_database_connections(self):
        """Dispose DB connections/engines via cleanup handler."""
        self.cleanup_handler.cleanup_database_connections(
            self.initializer.engine,
            self.initializer.entity_manager.event_tracker if hasattr(self.initializer.entity_manager, 'event_tracker') else None,
            self.initializer.entity_attribute_manager,
            self.initializer.resource_manager,
            self.initializer.queue_manager if hasattr(self.initializer, 'queue_manager') else None
        )
    
    
