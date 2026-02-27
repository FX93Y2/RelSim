"""
Database configuration parser
"""

import yaml
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Union

logger = logging.getLogger(__name__)

@dataclass
class Generator:
    type: str
    method: Optional[str] = None
    template: Optional[str] = None
    formula: Optional[str] = None        # Formula string support (e.g., "UNIF(3, 10)")
    expression: Optional[str] = None     # Expression string for formula type generators
    values: Optional[List] = None
    subtype: Optional[str] = None  # Added for foreign_key generator support

@dataclass
class Relationship:
    type: str
    multiplicity: Dict

@dataclass
class Attribute:
    name: str
    type: str
    generator: Optional[Generator] = None
    ref: Optional[str] = None
    relationship: Optional[Relationship] = None
    
    @property
    def is_primary_key(self) -> bool:
        return self.type == 'pk'
    
    @property
    def is_foreign_key(self) -> bool:
        return self.type == 'fk' or self.type == 'entity_id' or self.type == 'event_id' or self.type == 'resource_id'
    
    @property
    def is_entity_id(self) -> bool:
        return self.type == 'entity_id'
    
    @property
    def is_event_id(self) -> bool:
        return self.type == 'event_id'
    
    @property
    def is_resource_id(self) -> bool:
        return self.type == 'resource_id'
    
    @property
    def is_simulation_foreign_key(self) -> bool:
        """Check if this is a foreign key that will be handled by the simulation"""
        return self.type == 'entity_id' or self.type == 'event_id' or self.type == 'resource_id'

@dataclass
class Entity:
    name: str
    attributes: List[Attribute]
    rows: Any = 0
    type: Optional[str] = None  # Added to specify table type (entity, event, resource, etc.)

@dataclass
class DatabaseConfig:
    entities: List[Entity]

# Valid column types for strict validation
VALID_COLUMN_TYPES = {
    # Primary key
    'pk',

    # Foreign keys
    'entity_id',       # FK to entity table
    'event_id',        # FK to event table
    'resource_id',     # FK to resource table

    # Semantic column types (support parameterized versions)
    'event_type',         # Event type identifier
    'resource_type',      # Resource type identifier (for resource tables)
    
    # Integer types
    'integer', 'int', 'bigint', 'smallint', 'tinyint',
    
    # Decimal / floating-point types
    'decimal', 'numeric', 'float', 'double', 'real',
    
    # String types
    'string', 'text', 'varchar', 'char',
    
    # Temporal types
    'datetime', 'timestamp', 'date', 'time',
    
    # Boolean types
    'boolean', 'bool',
    
    # Legacy types (for backward compatibility during migration)
    'fk',  # Will be removed in future versions
}

# Required column types by table type
REQUIRED_TYPES_BY_TABLE = {
    'entity': ['pk'],
    'bridge': ['pk'],
    'event': ['pk', 'entity_id', 'event_type'],
    'resource': ['pk'],
}

def validate_entity_config(entity: Entity) -> None:
    """
    Validate entity configuration for required column types.
    
    Args:
        entity: Entity configuration to validate
        
    Raises:
        ValueError: If validation fails
    """
    # Check that all column types are valid
    for attr in entity.attributes:
        # Extract base type from parameterized types like decimal(10,2), varchar(100)
        base_type = attr.type.split('(')[0] if '(' in attr.type else attr.type
        
        if base_type not in VALID_COLUMN_TYPES:
            raise ValueError(
                f"Entity '{entity.name}' has invalid column type '{attr.type}' "
                f"in attribute '{attr.name}'. Valid base types: {sorted(VALID_COLUMN_TYPES)}"
            )
        
    
    # Check for required primary key
    pk_attrs = [attr for attr in entity.attributes if attr.type == 'pk']
    if len(pk_attrs) != 1:
        raise ValueError(
            f"Entity '{entity.name}' must have exactly one column with type='pk', "
            f"found {len(pk_attrs)}"
        )
    
    # Check table-specific requirements
    if entity.type in REQUIRED_TYPES_BY_TABLE:
        required_types = REQUIRED_TYPES_BY_TABLE[entity.type]
        # Extract base types to handle parameterized types like decimal(10,2)
        found_base_types = {attr.type.split('(')[0] if '(' in attr.type else attr.type for attr in entity.attributes}
        missing_types = set(required_types) - found_base_types
        
        if missing_types:
            raise ValueError(
                f"Table '{entity.name}' of type '{entity.type}' is missing required column types: "
                f"{sorted(missing_types)}. Required types: {sorted(required_types)}"
            )
    
    # Additional validations for specific table types
    if entity.type == 'event':
        _validate_event_table(entity)

def _validate_event_table(entity: Entity) -> None:
    """Validate event table specific requirements."""
    # Extract base types to handle parameterized types
    type_cols = [attr for attr in entity.attributes if (attr.type.split('(')[0] if '(' in attr.type else attr.type) == 'event_type']
    if len(type_cols) != 1:
        raise ValueError(
            f"Event table '{entity.name}' must have exactly one column with type='event_type'"
        )

def parse_db_config(file_path: Union[str, Path]) -> DatabaseConfig:
    if isinstance(file_path, str):
        file_path = Path(file_path)
        
    if not file_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    
    with open(file_path, 'r') as f:
        config_dict = yaml.safe_load(f)
    
    entities = []
    for entity_dict in config_dict.get('entities', []):
        attributes = []
        for attr_dict in entity_dict.get('attributes', []):
            generator = None
            if 'generator' in attr_dict:
                gen_dict = attr_dict['generator']
                generator = Generator(
                    type=gen_dict['type'],
                    method=gen_dict.get('method'),
                    template=gen_dict.get('template'),
                    formula=gen_dict.get('formula'),
                    expression=gen_dict.get('expression'),
                    values=gen_dict.get('values'),
                    subtype=gen_dict.get('subtype')
                )
            
            relationship = None
            if 'relationship' in attr_dict:
                rel_dict = attr_dict['relationship']
                relationship = Relationship(
                    type=rel_dict['type'],
                    multiplicity=rel_dict.get('multiplicity', {})
                )
            
            attributes.append(Attribute(
                name=attr_dict['name'],
                type=attr_dict['type'],
                generator=generator,
                ref=attr_dict.get('ref'),
                relationship=relationship
            ))
        
        entity = Entity(
            name=entity_dict['name'],
            attributes=attributes,
            rows=entity_dict.get('rows', 0),
            type=entity_dict.get('type')
        )
        
        # Validate entity configuration
        validate_entity_config(entity)
        
        entities.append(entity)
    
    config = DatabaseConfig(entities=entities)
    
    # Log validation success
    logger.info(f"Successfully parsed and validated {len(entities)} entities with strict column type validation")
    
    return config


def parse_db_config_from_string(content: str) -> DatabaseConfig:
    """
    Parse database configuration from YAML string with strict validation.
    
    Args:
        content: YAML configuration string
        
    Returns:
        Parsed and validated database configuration
        
    Raises:
        ValueError: If configuration is invalid or validation fails
    """
    try:
        config_dict = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML content: {e}")
    
    if not config_dict or 'entities' not in config_dict:
        raise ValueError("Configuration must contain 'entities' section")
    
    entities = []
    for entity_dict in config_dict['entities']:
        # Parse attributes
        attributes = []
        for attr_dict in entity_dict.get('attributes', []):
            generator = None
            if 'generator' in attr_dict:
                gen_dict = attr_dict['generator']
                generator = Generator(
                    type=gen_dict['type'],
                    method=gen_dict.get('method'),
                    template=gen_dict.get('template'),
                    formula=gen_dict.get('formula'),
                    expression=gen_dict.get('expression'), 
                    values=gen_dict.get('values'),
                    subtype=gen_dict.get('subtype')
                )
            
            relationship = None
            if 'relationship' in attr_dict:
                rel_dict = attr_dict['relationship']
                relationship = Relationship(
                    type=rel_dict['type'],
                    multiplicity=rel_dict.get('multiplicity', {})
                )
            
            attributes.append(Attribute(
                name=attr_dict['name'],
                type=attr_dict['type'],
                generator=generator,
                ref=attr_dict.get('ref'),
                relationship=relationship
            ))
        
        entity = Entity(
            name=entity_dict['name'],
            attributes=attributes,
            rows=entity_dict.get('rows', 0),
            type=entity_dict.get('type')
        )
        
        # Validate entity configuration
        validate_entity_config(entity)
        
        entities.append(entity)
    
    config = DatabaseConfig(entities=entities)
    
    # Log validation success
    logger.info(f"Successfully parsed and validated {len(entities)} entities from string with strict column type validation")
    
    return config 
