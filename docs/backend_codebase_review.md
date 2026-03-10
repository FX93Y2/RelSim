# RelSim: System Architecture & Developer Guide

## 1. System Purpose
**RelSim** is a specialized engine for generating synthetic relational databases that are **process-consistent**. Unlike standard data generators that create random rows, RelSim models the underlying time-based processes (e.g., Hospital Operations, E-Commerce Fulfillment) to ensure that the resulting data satisfies both **Referential Integrity** and **Temporal Logic**.

**Core Capability**: It combines a **Static Data Generator** (Faker-based) with a **Discrete-Event Simulation (DES)** engine (SimPy-based) to produce datasets where every timestamp and foreign key is the result of a simulated causal chain.

---

## 2. Core Concepts: The Entity-Resource-Event Model
The system enforces a strict architectural pattern to solve the "Many-to-Many Temporal Collision" problem:

1.  **Entities** (`Patient`, `Order`): Active agents that flow through the system.
2.  **Resources** (`Doctor`, `WarehousePicker`): Constrained assets required to perform tasks.
3.  **Bridge Tables / Events** (`Appointment`, `ClinicalEvent`):
    *   These are **Intersection Tables** connecting Entities and Resources.
    *   They act as the **Event Log**, recording exactly when an Entity seized a Resource (`start_time`) and released it (`end_time`).
    *   The system *automatically* populates these tables during simulation processing.
    *   **Chained Bridges**: Child bridge tables (e.g., `MedicationOrder`) can reference parent bridges (e.g., `ClinicalEvent`) via FK columns.

---

## 3. Data Generation Pipeline
The system operates in a strictly ordered 3-Phase Pipeline:

### Phase 1: Static Entity Generation (`src/generator`)
*   **Goal**: Populate base tables that exist independent of time (e.g., `Patient` list, `Inventory` catalog).
*   **Mechanism**:
    1.  **Parse Config**: Reads `db_config.yaml`.
    2.  **Dependency Sort**: Uses **Topological Sort** (`dependency_sorter.py`) to determine the creation order of tables to satisfy Foreign Keys.
    3.  **Populate**: Uses `DataPopulator` to insert rows.
    4.  **Defer**: Attributes marked with formulas (e.g., "TotalCost") are skipped (set to SQL NULL) to be resolved later.
*   **Custom PK Generators**:
    *   PKs can use `template` (e.g., `INV{id}`) or `faker` (e.g., UUID) generators.
    *   `table_builder.py` dynamically chooses `String` vs `Integer` column types based on the generator.
    *   Template PKs use `COUNT(*)+1` for sequential numbering.

### Phase 2: Discrete-Event Simulation (`src/simulation`)
*   **Goal**: Generate transaction history and link Entities to Resources.
*   **Mechanism**:
    1.  **Initialize**: Loads `sim_config.yaml` and initializes a **SimPy Environment**.
    2.  **Flow Kickoff**: For each defined Flow (e.g., "Patient Arrival"), `FlowManager` starts a generator process that creates Entities at defined intervals (`interarrival_time`).
    3.  **Step Execution**: Entities move through steps:
        *   `Create`: Instantiates the active Entity.
        *   **`Event`**: The core step. The Entity requests a Resource.
            *   *Queueing*: If Resource is busy, Entity waits (SimPy `Resource.request()`).
            *   *Processing*: Once seized, simulation clock advances by `duration`.
            *   *Logging*: The `EventTracker` writes a record to the **Bridge Table** (`entity_id`, `resource_id`, `start_time`, `end_time`).
            *   *Resource Grouping*: Steps with the same `group_id` share allocated resources without re-acquiring.
        *   `Decide`: Branches flow based on probability or data conditions.
        *   `Trigger`: Creates related records mid-flow (e.g., `Invoice` after medication order).
        *   `Assign`: Executes SQL assignments with `Entity.property` substitution.
        *   `Release`: Frees the Resource.

### Phase 3: Dependent Logic (`src/generator/data/formula`)
*   **Goal**: Calculate derived attributes that depend on Phase 2 results.
*   **Mechanism**:
    1.  **Analyze**: Identifies columns marked as `formula` (e.g., `Invoice.TotalAmount`).
    2.  **Resolve**: The `FormulaResolver` iterates through rows, solving expressions (e.g., `SUM(Prescription.Cost)`) using the now-complete Phase 2 data.
    3.  **Update**: SQL Updates are issued to finalize the database.

---

## 4. Key Components & Algorithms

### A. Configuration Parsing (`src/config_parser`)
*   **`db_parser.py`**:
    *   Enforces strict typing: `pk`, `fk`, `entity_id`, `resource_id`, `event_type`.
    *   Validates that Event Tables have exactly one `event_type` column.
    *   Parses Generators: `faker` (string/UUID), `template` (sequential IDs), `distribution` (numerical), `formula` (derived), `foreign_key` (FK selection with formula support).
*   **`sim_parser.py`**:
    *   Parses **Step Logic**: `create` -> `event` -> `decide` -> `trigger` -> `assign` -> `release`.
    *   Parses **Distributions**: `UNIF(a,b)`, `NORM(mean,std)`, `EXPO(lambda)`.
    *   Parses **Resource Grouping**: `group_id` field for resource sharing across steps.

### B. Dependency Sorting (`src/generator/schema/dependency_sorter.py`)
*   **Algorithm**: Topological Sort (Depth-First Search).
*   **Logic**:
    *   Builds a generic graph where Nodes = Tables and Edges = Foreign Key dependencies.
    *   Detects **Circular Dependencies** (e.g., A -> B -> A) and raises `ValueError`.
    *   Returns a linear execution list for `DataPopulator`.

### C. Simulation Engine (`src/simulation/core`)
*   **`runner.py`**: Principal entry point. Requires *both* DB and Sim configs.
*   **`simulator.py`**: Main simulation loop orchestration.
*   **Core Sub-packages**:
    *   **`initialization/`**: Setup phase
        *   `config_loader.py`: Parses and validates configurations
        *   `resource_setup.py`: Initializes SimPy resources
        *   `tracker_setup.py`: Dynamic Bridge Detection and EventTracker wiring
    *   **`execution/`**: Runtime flow management
        *   `flow_manager.py`: Starts entity generator processes per flow
        *   `entity_router.py`: Routes entities through steps
        *   `step_executor.py`: Delegates to step processors
    *   **`lifecycle/`**: Monitoring and cleanup
        *   `metrics.py`: `MetricsCollector` for resource/entity/queue statistics
        *   `termination.py`: Handles simulation end conditions
        *   `cleanup.py`: Database connection and resource cleanup

### D. Event Tracking (`src/simulation/managers/event_tracker.py`)
*   **Dynamic Bridge Detection**: Scans `db_config` for tables containing both `entity_id` (pointing to the Flow's Entity) and `resource_id` (pointing to the Flow's Resource).
*   **Auto-Wiring**: Instantiates an `EventTracker` wired to that specific Bridge Table.
*   **Chained Bridges**: Supports parent-child bridge relationships via FK columns.
*   **PK Generation**: Handles both auto-increment and custom template-based PKs for bridge records.

### E. Resource Management (`src/simulation/managers/resource_manager.py`)
*   **SimPy FilterStore**: Uses FilterStore for efficient resource pooling and individual tracking.
*   **Resource Allocation**: Manages the SimPy `yield env.timeout(duration)` call.
*   **Resource Seizure & Release**: Via `allocate_resources()` and `release_resources()`.
*   **Resource Grouping**: Steps with the same `group_id` reuse allocated resources without re-acquiring.
*   **Utilization Statistics**: Tracks allocation history and utilization rates.

### F. Queue Management (`src/simulation/managers/queue_manager.py`)
*   **Arena-style Disciplines**:
    *   `FIFO`: First-In-First-Out (standard queue)
    *   `LIFO`: Last-In-First-Out (stack)
    *   `LowAttribute`: Priority queue (lower attribute values first)
    *   `HighAttribute`: Priority queue (higher values first)
*   **Database Logging**: Creates `sim_queue_activity` table for entry/exit events.
*   **Statistics**: Tracks wait times, queue lengths, entry/exit counts, and throughput.
*   **Entity Priority**: Supports attribute-based priority calculation for queue ordering.

### G. Entity Management (`src/simulation/managers`)
*   **`entity_manager.py`**:
    *   Creates entities with proper attribute generation (Faker, distributions).
    *   Handles FK resolution and template-based PK generation.
    *   Updates entity attributes during simulation.
*   **`entity_attribute_manager.py`**:
    *   Thread-safe in-memory storage for entity attributes.
    *   Supports Arena-style Assign module functionality.
    *   Falls back to database lookup when attributes not in memory.

### H. Step Processors (`src/simulation/processors`)
*   **Factory Pattern** (`factory.py`):
    *   `StepProcessorFactory`: Routes step processing to appropriate processors.
    *   Dynamic processor registration and validation.
    *   Supports custom processor addition.
*   **Processor Types**:
    *   `create/processor.py`: Entity creation with interarrival time distributions.
    *   `event/processor.py`: Resource seizure, bridge table logging, duration handling.
    *   `decide/processor.py`: Probability-based and condition-based branching.
    *   `trigger/processor.py`: Mid-flow record creation with custom PK generation.
    *   `assign/processor.py`: Attribute and SQL assignments with `Entity.property` substitution.
    *   `release/processor.py`: Resource release handling.

### I. Distribution System (`src/distributions`)
*   **Formula Parsing** (`formula_parser.py`): Parses formula strings like `UNIF(3, 10)`, `DISC(0.7, 'A', 0.3, 'B')`.
*   **Registry** (`registry.py`): Centralized factory (`DistributionRegistry`) for all distributions with alias support.
*   **Supported Distributions** (13+):
    *   **Continuous**: `UNIF`, `NORM`, `EXPO`, `TRIA`, `BETA`, `GAMA`, `ERLA`, `LOGN`, `WEIB`
    *   **Discrete**: `POIS`, `DISC`
    *   **Special**: `RAND`, `FIXED`
*   **Generators**: Modular implementations in `generators/continuous.py`, `generators/discrete.py`, `generators/special.py`.

### J. Time Unit System (`src/utils/time_units.py`)
*   **Internal Base Unit**: All simulation time calculations use **minutes** internally.
*   **Supported Units**: `seconds`, `minutes`, `hours`, `days`.
*   **`TimeUnit` Enum**: Conversion factors (e.g., `HOURS = 60`, `DAYS = 1440`).
*   **`TimeUnitConverter`**: Static utility for conversions:
    *   `to_minutes(value, from_unit)`: Convert to base unit.
    *   `from_minutes(minutes, to_unit)`: Convert from base unit.
    *   `convert(value, from_unit, to_unit)`: Direct conversion.

### K. Termination Conditions (`src/simulation/termination`)
*   **Formula Language**: Human-readable expressions like `TIME(720) OR ENTITIES(Order, 1000)`.
*   **`TerminationFormulaParser`**: Recursive descent parser for condition trees.
*   **Condition Types**:
    *   `TimeCondition`: `TIME(minutes)` - Stop after elapsed simulation time.
    *   `EntitiesCondition`: `ENTITIES(table, count)` - Stop after N entities created.
    *   `EventsCondition`: `EVENTS(count)` - Stop after N events processed.
*   **Logical Operators**: `AND`, `OR` with parentheses for grouping.
*   **Example**: `(TIME(1440) AND ENTITIES(Patient, 100)) OR EVENTS(500)`

### L. Post-Sim Formulas (`src/generator/data/formula`)
*   **`resolver.py`**: Main formula resolution orchestration.
*   **`evaluator.py`**: SQL-like expression evaluation.
*   **`parser.py`**: Formula syntax parsing.
*   **Logic**:
    *   Loads rows into a generic dictionary context.
    *   Evaluates SQL-like expressions using safe evaluation.
    *   Supports special accessors like `MIN(related_table.date)` for time-based derivations.

---

## 5. API Surface (`python/api`)
The Flask API is organized into modular blueprints registered under `/api`:

### Core Operations
*   `POST /api/simulation/generate`: Runs Phase 1 (Database Generation).
*   `POST /api/simulation/run`: Runs Phase 2 (Simulation on existing DB).
*   `POST /api/simulation/generate-and-simulate`: Full pipeline (Phases 1 → 2 → 3).

### Project Management (`routes/projects.py`)
*   `GET /api/projects`: List all projects.
*   `POST /api/projects`: Create a new project.
*   `GET /api/projects/<id>`: Retrieve project details.
*   `PUT /api/projects/<id>`: Update project.
*   `DELETE /api/projects/<id>`: Delete project and associated configurations.

### Configuration Management (`routes/configurations.py`)
*   `GET /api/configurations/<project_id>/<type>`: Get configuration by type (database/simulation).
*   `POST /api/configurations/<project_id>/<type>`: Save or update configuration.
*   `DELETE /api/configurations/<id>`: Delete a configuration.

### Results & Validation
*   `GET /api/results/<project_id>`: Retrieve simulation results and output files.
*   `POST /api/validation/database`: Validate database schema configuration.
*   `POST /api/validation/simulation`: Validate simulation configuration.

### Server Architecture
*   **`server.py`**: Flask app factory with CORS, error handlers, and blueprint registration.
*   **`middleware/error_handlers.py`**: Centralized exception handling.
*   **`utils/`**: Shared utilities for path resolution and request handling.

---

## 6. Configuration Storage (`config_storage/config_db.py`)
SQLite-based persistence for projects and configurations used by the Electron frontend.

*   **`ConfigManager`** Class:
    *   `create_project(name)` / `get_project(id)` / `delete_project(id)`
    *   `save_project_config(project_id, type, content)`
    *   `get_project_configs(project_id)`
    *   Automatic schema initialization on first run.
*   **Database Schema**:
    *   `projects`: id, name, description, created_at, updated_at
    *   `configurations`: id, project_id, config_type (database/simulation), name, content (YAML), description
*   **Environment Variable**: `DB_SIMULATOR_CONFIG_DB` for custom database path.

---

## 7. Directory Structure
```
python/
├── api/                         # Flask API Server
│   ├── routes/                  # Modular route blueprints
│   │   ├── configurations.py    # Configuration CRUD
│   │   ├── database.py          # Database generation
│   │   ├── projects.py          # Project management
│   │   ├── results.py           # Results retrieval
│   │   ├── simulation.py        # Simulation execution
│   │   └── validation.py        # Schema validation
│   ├── middleware/              # Error handlers
│   ├── utils/                   # API utilities
│   └── server.py                # Flask app factory
├── config_storage/              # Persistent Configuration
│   └── config_db.py             # SQLite-based ConfigManager
├── src/
│   ├── config_parser/           # YAML Configuration Parsers
│   │   ├── db_parser.py         # Database schema parser
│   │   └── sim_parser.py        # Simulation config parser (dataclasses)
│   ├── distributions/           # Probability Distribution System
│   │   ├── formula_parser.py    # Formula string parser
│   │   ├── registry.py          # Distribution factory
│   │   ├── core.py              # Main generation interface
│   │   └── generators/          # Distribution implementations
│   │       ├── continuous.py    # UNIF, NORM, EXPO, TRIA, BETA, etc.
│   │       ├── discrete.py      # POIS, DISC
│   │       └── special.py       # RAND, FIXED
│   ├── generator/               # Database Generation (Phase 1)
│   │   ├── schema/
│   │   │   ├── table_builder.py     # SQLAlchemy table creation
│   │   │   └── dependency_sorter.py # Topological sort for FKs
│   │   ├── data/
│   │   │   ├── populator.py         # Row insertion logic
│   │   │   ├── faker_js/            # Faker.js bridge for Python
│   │   │   ├── foreign_key/         # FK resolution
│   │   │   ├── formula/             # Formula evaluation (Phase 3)
│   │   │   └── template/            # Template-based PK generation
│   │   └── database_generator.py    # Main generator orchestration
│   ├── simulation/              # Discrete Event Simulation (Phase 2)
│   │   ├── core/
│   │   │   ├── runner.py            # Entry point
│   │   │   ├── simulator.py         # Main simulation loop
│   │   │   ├── initialization/      # Setup: config, resources, trackers
│   │   │   │   ├── config_loader.py
│   │   │   │   ├── resource_setup.py
│   │   │   │   └── tracker_setup.py
│   │   │   ├── execution/           # Flow management, entity routing
│   │   │   │   ├── flow_manager.py
│   │   │   │   ├── entity_router.py
│   │   │   │   └── step_executor.py
│   │   │   └── lifecycle/           # Metrics, cleanup, termination
│   │   │       ├── metrics.py
│   │   │       ├── cleanup.py
│   │   │       └── termination.py
│   │   ├── managers/
│   │   │   ├── resource_manager.py      # SimPy FilterStore-based allocation
│   │   │   ├── event_tracker.py         # Bridge table logging
│   │   │   ├── entity_manager.py        # Entity creation
│   │   │   ├── entity_attribute_manager.py # In-memory attribute storage
│   │   │   └── queue_manager.py         # Arena-style queue disciplines
│   │   ├── processors/              # Step Implementations
│   │   │   ├── factory.py           # Processor factory pattern
│   │   │   ├── base.py              # Base processor class
│   │   │   ├── create/              # Entity creation
│   │   │   ├── event/               # Resource seizure + bridge logging
│   │   │   ├── decide/              # Conditional branching
│   │   │   ├── trigger/             # Mid-flow record creation
│   │   │   ├── assign/              # Attribute assignments
│   │   │   └── release/             # Resource release
│   │   ├── termination/             # Termination Condition System
│   │   │   ├── formula.py           # TIME/ENTITIES/EVENTS parser
│   │   │   └── TERMINATION_CONDITIONS.md
│   │   └── utils/
│   │       ├── sql_helpers.py       # Entity.property substitution
│   │       └── column_resolver.py   # Dynamic column lookup
│   └── utils/                       # Shared Utilities
│       ├── time_units.py            # Time unit conversion
│       ├── db_utils.py              # Database connection helpers
│       ├── path_resolver.py         # Output directory resolution
│       └── file_operations.py       # File I/O utilities
├── tests/                           # Pytest suite
├── main.py                          # CLI entry point
└── requirements.txt                 # Python dependencies
```

---

## 8. Environment Variables
| Variable | Purpose |
|----------|---------|
| `DB_SIMULATOR_OUTPUT_DIR` | Target directory for generated database files |
| `DB_SIMULATOR_CONFIG_DB` | Path to internal configuration database |
| `DB_SIMULATOR_PACKAGED` | Set when running in frozen/packaged mode (PyInstaller) |
| `DB_SIMULATOR_LOG_FILE` | Optional file path for logging output |
| `PORT` | Flask server port (default: 5000) |
