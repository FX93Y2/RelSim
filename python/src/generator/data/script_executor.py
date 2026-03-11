"""
Script executor for user-provided Python scripts.

Loads and executes custom Python scripts that generate table data,
allowing complex rule-based data generation beyond what built-in
generators (faker, distributions) can express.
"""

import os
import logging
import importlib.util
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ...config_parser import DatabaseConfig, Entity

logger = logging.getLogger(__name__)


class ScriptExecutionError(Exception):
    """Raised when a user script fails during execution."""

    def __init__(self, script_path: str, original_error: Exception, tb: str):
        self.script_path = script_path
        self.original_error = original_error
        self.traceback = tb
        super().__init__(
            f"Script '{script_path}' failed: {original_error}\n\n"
            f"--- Script Traceback ---\n{tb}"
        )


@dataclass
class ScriptContext:
    """
    Context object passed to user scripts.

    Attributes:
        session:  SQLAlchemy session (read existing data, but don't insert — return rows instead)
        models:   Dict mapping table names to SQLAlchemy model classes
        config:   Full parsed DatabaseConfig
        entity:   This table's Entity config
        logger:   Logger instance (messages appear in app log panel)
    """
    session: Any
    models: Dict[str, Any]
    config: DatabaseConfig
    entity: Entity
    logger: logging.Logger


class ScriptExecutor:
    """Loads and executes user-provided Python scripts for table generation."""

    def execute(
        self,
        entity: Entity,
        session: Any,
        models: Dict[str, Any],
        config: DatabaseConfig,
        project_dir: str,
    ) -> int:
        """
        Load and run the user's script, then insert returned rows.

        Args:
            entity:      Entity config (must have entity.generator with type='script')
            session:     SQLAlchemy session
            models:      Dict of all table model classes
            config:      Full DatabaseConfig
            project_dir: Project root directory (script paths are relative to this)

        Returns:
            Number of rows inserted

        Raises:
            ScriptExecutionError: If the script fails to load or execute
            FileNotFoundError: If the script file doesn't exist
            ValueError: If the script is misconfigured
        """
        generator = entity.generator
        if not generator or generator.type != 'script':
            raise ValueError(
                f"Entity '{entity.name}' does not have a script generator"
            )

        # Resolve script path
        script_path = self._resolve_script_path(generator.path, project_dir)
        function_name = generator.function or 'generate'

        logger.info(
            f"Executing script for table '{entity.name}': "
            f"{script_path}:{function_name}()"
        )

        # Load the script module
        module = self._load_module(script_path, entity.name)

        # Get the entry function
        func = self._get_function(module, function_name, script_path)

        # Build context
        script_logger = logging.getLogger(f"script.{entity.name}")
        context = ScriptContext(
            session=session,
            models=models,
            config=config,
            entity=entity,
            logger=script_logger,
        )

        # Execute the script
        rows = self._call_function(func, context, script_path)

        # Validate and insert rows
        row_count = self._insert_rows(rows, entity, models, session)

        logger.info(
            f"Script for table '{entity.name}' generated {row_count} rows"
        )
        return row_count

    def _resolve_script_path(self, path: Optional[str], project_dir: Optional[str]) -> str:
        """Resolve the script path relative to the project directory."""
        if not path:
            raise ValueError("Script generator missing 'path' field")

        if os.path.isabs(path):
            script_path = path
        else:
            # Fall back to CWD if no project_dir provided
            base_dir = project_dir or os.getcwd()
            script_path = os.path.join(base_dir, path)

        script_path = os.path.abspath(script_path)

        if not os.path.exists(script_path):
            raise FileNotFoundError(
                f"Script file not found: {script_path}\n"
                f"(resolved from path='{path}', project_dir='{project_dir or 'CWD'}')"
            )

        return script_path

    def _load_module(self, script_path: str, entity_name: str):
        """Load a Python module from a file path using importlib."""
        module_name = f"_script_{entity_name}"

        try:
            spec = importlib.util.spec_from_file_location(module_name, script_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not create module spec from: {script_path}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        except Exception as e:
            if isinstance(e, (ScriptExecutionError, FileNotFoundError)):
                raise
            tb = traceback.format_exc()
            raise ScriptExecutionError(script_path, e, tb)

    def _get_function(self, module, function_name: str, script_path: str):
        """Get the entry point function from the loaded module."""
        if not hasattr(module, function_name):
            available = [
                name for name in dir(module)
                if callable(getattr(module, name)) and not name.startswith('_')
            ]
            raise ScriptExecutionError(
                script_path,
                AttributeError(
                    f"Function '{function_name}' not found in script. "
                    f"Available functions: {available}"
                ),
                f"Function '{function_name}' not found"
            )

        func = getattr(module, function_name)
        if not callable(func):
            raise ScriptExecutionError(
                script_path,
                TypeError(f"'{function_name}' is not callable"),
                f"'{function_name}' is not a callable function"
            )

        return func

    def _call_function(self, func, context: ScriptContext, script_path: str) -> List[dict]:
        """Call the user's function and validate the return value."""
        try:
            result = func(context)
        except Exception as e:
            tb = traceback.format_exc()
            raise ScriptExecutionError(script_path, e, tb)

        # Validate return type
        if result is None:
            logger.warning(
                f"Script '{script_path}' returned None — treating as empty list"
            )
            return []

        if not isinstance(result, list):
            raise ScriptExecutionError(
                script_path,
                TypeError(
                    f"Script must return List[dict], got {type(result).__name__}"
                ),
                f"Invalid return type: {type(result).__name__}"
            )

        # Validate individual items
        for i, row in enumerate(result):
            if not isinstance(row, dict):
                raise ScriptExecutionError(
                    script_path,
                    TypeError(
                        f"Row {i} must be a dict, got {type(row).__name__}"
                    ),
                    f"Invalid row type at index {i}: {type(row).__name__}"
                )

        return result

    def _insert_rows(
        self,
        rows: List[dict],
        entity: Entity,
        models: Dict[str, Any],
        session: Any,
    ) -> int:
        """Insert the script-generated rows into the database."""
        if not rows:
            logger.info(f"Script for '{entity.name}' returned 0 rows")
            return 0

        model_class = models.get(entity.name)
        if model_class is None:
            raise ValueError(
                f"No SQLAlchemy model found for table '{entity.name}'"
            )

        # Get valid column names and their types from the model
        valid_columns = set(model_class.__table__.columns.keys())
        column_types = {
            col.name: col.type
            for col in model_class.__table__.columns
        }

        inserted = 0
        for i, row_data in enumerate(rows):
            # Filter to valid columns only, warn about extras
            filtered_data = {}
            for key, value in row_data.items():
                if key in valid_columns:
                    # Auto-coerce types for common mismatches
                    filtered_data[key] = self._coerce_value(
                        value, column_types.get(key), key, i, entity.name
                    )
                else:
                    logger.warning(
                        f"Script row {i} for '{entity.name}': "
                        f"ignoring unknown column '{key}'"
                    )

            try:
                record = model_class(**filtered_data)
                session.add(record)
                inserted += 1
            except Exception as e:
                logger.error(
                    f"Error inserting script row {i} for '{entity.name}': {e}. "
                    f"Row data: {filtered_data}"
                )
                raise

        # Flush to make rows visible for subsequent script tables
        session.flush()

        return inserted

    @staticmethod
    def _coerce_value(value, column_type, column_name: str, row_index: int, table_name: str):
        """
        Auto-coerce script values to match SQLAlchemy column types.
        Handles common cases like string → date, string → datetime, string → int/float.
        """
        if value is None:
            return None

        from sqlalchemy import Date, DateTime, Integer, Float, Numeric, Boolean, String, Text

        # Already the right type — skip
        if column_type is None:
            return value

        try:
            # Date columns: accept strings in ISO format (YYYY-MM-DD)
            if isinstance(column_type, Date) and not isinstance(column_type, DateTime):
                if isinstance(value, str):
                    from datetime import date as date_type, datetime as datetime_type
                    # Try ISO format first
                    try:
                        return datetime_type.strptime(value, "%Y-%m-%d").date()
                    except ValueError:
                        return datetime_type.fromisoformat(value).date()
                from datetime import date as date_type
                if isinstance(value, date_type):
                    return value

            # DateTime columns: accept strings and date objects
            if isinstance(column_type, DateTime):
                if isinstance(value, str):
                    from datetime import datetime as datetime_type
                    return datetime_type.fromisoformat(value)
                from datetime import date as date_type, datetime as datetime_type
                if isinstance(value, date_type) and not isinstance(value, datetime_type):
                    return datetime_type.combine(value, datetime_type.min.time())

            # Integer columns
            if isinstance(column_type, Integer) and isinstance(value, str):
                return int(value)

            # Float/Numeric columns
            if isinstance(column_type, (Float, Numeric)) and isinstance(value, str):
                return float(value)

            # Boolean columns
            if isinstance(column_type, Boolean) and isinstance(value, str):
                return value.lower() in ('true', '1', 'yes')

        except (ValueError, TypeError) as e:
            logger.warning(
                f"Could not coerce value for '{table_name}'.'{column_name}' "
                f"(row {row_index}): {value!r} → {e}. Using original value."
            )

        return value

