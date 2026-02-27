"""
SQLAlchemy table creation for database entities.

This module handles the creation of SQLAlchemy model classes
and database tables from configuration.
"""

import logging
from typing import Any, Dict

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Numeric, Float, Boolean, Text, Date, Time
from sqlalchemy.ext.declarative import declarative_base

from ...config_parser import DatabaseConfig, Entity

logger = logging.getLogger(__name__)


class TableBuilder:
    """Handles creation of SQLAlchemy tables from entity configuration."""
    
    def __init__(self):
        """Initialize the table builder."""
        self.Base = declarative_base()
        self.models = {}
    
    def create_tables(self, config: DatabaseConfig, engine, flow_attributes: Dict[str, Dict[str, Dict[str, Any]]] = None):
        """
        Create tables based on configuration
        
        Args:
            config: Database configuration
            engine: SQLAlchemy engine
            flow_attributes: Flow-specific attributes from simulation analysis
        """
        self.flow_attributes = flow_attributes or {}
        
        # First pass: Create model classes for all entities
        for entity in config.entities:
            self._create_model_class(entity)
        
        # Create all tables
        self.Base.metadata.create_all(engine)
        
        return self.models
    
    def _create_model_class(self, entity: Entity):
        """
        Create SQLAlchemy model class for an entity
        
        Args:
            entity: Entity configuration
        """
        attrs = {
            '__tablename__': entity.name,
            '__table_args__': {'extend_existing': True}
        }
        
        # Add columns based on attributes
        for attr in entity.attributes:
            column_type = self._get_column_type(attr.type)
            
            # Handle primary key
            if attr.is_primary_key:
                # Check if PK has a custom generator (e.g., faker for UUID)
                if attr.generator and getattr(attr.generator, 'type', None) == 'faker':
                    # Faker-generated PKs are typically strings (UUIDs)
                    attrs[attr.name] = Column(String, primary_key=True)
                elif attr.generator and getattr(attr.generator, 'type', None) == 'template':
                    # Template-generated PKs are strings
                    attrs[attr.name] = Column(String, primary_key=True)
                else:
                    # Default: Integer auto-increment
                    attrs[attr.name] = Column(Integer, primary_key=True)
            
            # Handle foreign key
            elif attr.is_foreign_key and attr.ref:
                ref_table, ref_column = attr.ref.split('.')
                attrs[attr.name] = Column(Integer, ForeignKey(f"{ref_table}.{ref_column}"))
            
            # Handle regular columns
            else:
                attrs[attr.name] = Column(column_type)
        
        # Add automatic created_at column for entity tables
        if entity.type == 'entity':
            attrs['created_at'] = Column(DateTime, nullable=True)
            logger.debug(f"Added automatic created_at column to entity table '{entity.name}'")
        
        # Add flow-specific simulation attribute columns for entity tables only
        if entity.type == 'entity' and self.flow_attributes:
            entity_attrs = self._get_attributes_for_entity(entity.name)
            if entity_attrs:
                logger.info(f"Adding {len(entity_attrs)} flow-specific attribute columns to entity table '{entity.name}'")
                for attr_name, attr_type in entity_attrs.items():
                    attrs[attr_name] = Column(attr_type, nullable=True)
                    logger.debug(f"Added column: {entity.name}.{attr_name} ({attr_type.__name__})")
            else:
                logger.debug(f"No flow-specific attributes found for entity table '{entity.name}'")

        # Add default lifecycle columns for bridge tables that link entities and resources
        if entity.type == 'bridge':
            attr_names = {attr.name for attr in entity.attributes}
            attr_types = {attr.type for attr in entity.attributes}
            has_entity_fk = any(attr.type == 'entity_id' for attr in entity.attributes)
            has_resource_fk = any(attr.type == 'resource_id' for attr in entity.attributes)

            if has_entity_fk and has_resource_fk:
                # Ensure an event type marker exists
                if 'event_type' not in attr_names and 'event_type' not in attr_types:
                    attrs['event_type'] = Column(String, nullable=True)
                    logger.debug(f"Added default event_type column to bridge table '{entity.name}'")

                # Ensure lifecycle timestamps exist
                if 'start_date' not in attr_names:
                    attrs['start_date'] = Column(DateTime, nullable=True)
                    logger.debug(f"Added default start_date column to bridge table '{entity.name}'")
                if 'end_date' not in attr_names:
                    attrs['end_date'] = Column(DateTime, nullable=True)
                    logger.debug(f"Added default end_date column to bridge table '{entity.name}'")
        
        # Create model class
        model_class = type(entity.name, (self.Base,), attrs)
        self.models[entity.name] = model_class
    
    def _get_column_type(self, attr_type: str) -> Any:
        """
        Map attribute type to SQLAlchemy column type
        
        Args:
            attr_type: Attribute type from configuration
            
        Returns:
            SQLAlchemy column type
        """
        # Handle parameterized types like decimal(10,2), varchar(50)
        if '(' in attr_type:
            base_type = attr_type.split('(')[0].lower()
            params = attr_type.split('(')[1].rstrip(')').split(',')

            if base_type == 'decimal' or base_type == 'numeric':
                precision = int(params[0]) if len(params) > 0 else 10
                scale = int(params[1]) if len(params) > 1 else 2
                return Numeric(precision, scale)
            elif base_type == 'varchar':
                length = int(params[0]) if len(params) > 0 else 255
                return String(length)
            elif base_type == 'char':
                length = int(params[0]) if len(params) > 0 else 1
                return String(length)
        
        type_map = {
            'pk': Integer,
            'fk': Integer,
            'entity_id': Integer,
            'event_id': Integer,
            'resource_id': Integer,
            'event_type': String,
            'resource_type': String,
            'integer': Integer,
            'int': Integer,
            'bigint': Integer,
            'smallint': Integer,
            'tinyint': Integer,
            'decimal': Numeric,
            'numeric': Numeric,
            'float': Float,
            'double': Float,
            'real': Float,
            'string': String,
            'varchar': String,
            'char': String,
            'text': Text,
            'boolean': Boolean,
            'bool': Boolean,
            'datetime': DateTime,
            'timestamp': DateTime,
            'date': Date,
            'time': Time,
        }
        
        return type_map.get(attr_type.lower(), String)
    
    def _get_attributes_for_entity(self, entity_name: str) -> Dict[str, Any]:
        """
        Get all attributes that should be added to a specific entity table.
        
        Args:
            entity_name: Name of the entity table
            
        Returns:
            Dictionary mapping attribute names to their SQLAlchemy column types
        """
        entity_attributes = {}
        
        # Search through all flows to find attributes for this entity
        for flow_id, entities in self.flow_attributes.items():
            if entity_name in entities:
                # Merge attributes from this flow
                for attr_name, attr_type in entities[entity_name].items():
                    if attr_name in entity_attributes:
                        # If attribute exists from multiple flows, use most general type
                        if entity_attributes[attr_name] != attr_type:
                            entity_attributes[attr_name] = String
                    else:
                        entity_attributes[attr_name] = attr_type
                    
                    logger.debug(f"Entity {entity_name} gets attribute {attr_name} from flow {flow_id}")
        
        return entity_attributes
