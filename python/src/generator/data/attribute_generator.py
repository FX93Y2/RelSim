"""
Attribute value generation for database entities.

This module generates values for entity attributes based on their generator configuration,
supporting various generation methods including distribution formulas, Faker, and templates.
"""

import logging
import random
from typing import Any, Dict

from .faker_js import generate_fake_data
from .template import generate_from_template

logger = logging.getLogger(__name__)


def generate_attribute_value(attr_config: Dict[str, Any], row_index: int) -> Any:
    """
    Generate value for an attribute based on its generator configuration.

    Args:
        attr_config: Attribute configuration dictionary containing 'name' and 'generator' keys
        row_index: Index of the current row being generated (0-based)

    Returns:
        The generated value for the attribute

    Examples:
        # Template generator
        generate_attribute_value({
            'name': 'title',
            'generator': {'type': 'template', 'template': 'ticket_{id}'}
        }, 0)  # Returns 'ticket_1'
        
        # Formula distribution
        generate_attribute_value({
            'name': 'priority', 
            'generator': {'type': 'distribution', 'formula': 'DISC(0.7, "low", 0.3, "high")'}
        }, 0)  # Returns 'low' or 'high'
        
        # Faker generator
        generate_attribute_value({
            'name': 'description',
            'generator': {'type': 'faker', 'method': 'sentence'}
        }, 0)  # Returns fake sentence
    """
    generator_config = attr_config.get('generator')
    attr_name = attr_config.get('name', 'unknown_attr')

    if not generator_config:
        return f"Default_{attr_name}_{row_index}"

    generator_type = generator_config.get('type')

    # Faker generator
    if generator_type == 'faker':
        method = generator_config.get('method')
        if method:
            return generate_fake_data(method)
        else:
            logger.warning(f"Faker generator missing method for {attr_name}")
            return f"Faker_{attr_name}_{row_index}"

    # Template generator
    elif generator_type == 'template':
        template = generator_config.get('template') or "{id}"
        # Use row_index + 1 for 1-based ID in template context
        id_offset = generator_config.get('id_offset') or 0
        context = {'id': row_index + 1 + id_offset} 
        try:
            return generate_from_template(template, context)
        except Exception as e:
            logger.warning(f"Error in template for {attr_name}: {e}. Context: {context}")
            return f"Template_Error_{attr_name}_{row_index}"

    # Distribution generator - supports both formula and dict formats
    elif generator_type == 'distribution':
        # Check for formula first (preferred new format)
        formula = generator_config.get('formula')
        if formula:
            try:
                from ...distributions import generate_from_distribution
                return generate_from_distribution(formula)
            except Exception as e:
                logger.error(f"Error generating from formula '{formula}' for {attr_name}: {e}")
                raise
        
        logger.error(f"Distribution generator for {attr_name} missing 'formula' field")
        raise ValueError(f"Invalid distribution generator config for {attr_name}: formula field is required")

    # Ordered list generator - assigns values by row index (deterministic, one-of-each)
    elif generator_type == 'ordered_list':
        values = generator_config.get('values', [])
        if not values:
            logger.warning(f"Ordered list generator for {attr_name} has no values")
            return f"OrderedList_{attr_name}_{row_index}"
        # Cycle through values if there are more rows than values
        return values[row_index % len(values)]

    # Simulation event type - handled by simulation system
    elif generator_type == 'simulation_event':
        values = generator_config.get('values', [])
        if values:
            return None  # Let simulation handle this
        return f"SimEvent_{attr_name}_{row_index}"
    
    # Foreign key generator - handled by database generator
    elif generator_type == 'foreign_key':
        # Foreign key resolution is handled by the database generator
        # or simulator's entity creation methods
        return None

    # Unknown generator type
    else:
        logger.warning(f"Unknown generator type '{generator_type}' for {attr_name}")
        return f"Value_{generator_type or 'Unknown'}_{attr_name}_{row_index}"