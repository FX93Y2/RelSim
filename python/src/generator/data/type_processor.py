"""
Type-aware value processing for database attributes.

This module provides utilities to format generated values according to their
specified data types (decimal precision, integer rounding, etc.).
"""

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def process_value_for_type(value: Any, attr_type: str) -> Any:
    """
    Process a generated value to match the expected data type format.
    
    Args:
        value: The generated value
        attr_type: The attribute's data type specification
        
    Returns:
        The processed value formatted for the data type
    """
    if value is None:
        return None
        
    # Handle parameterized types like decimal(10,2), varchar(50)
    if '(' in attr_type:
        base_type = attr_type.split('(')[0].lower()
        params = attr_type.split('(')[1].rstrip(')').split(',')
        
        if base_type in ['decimal', 'numeric']:
            # Extract precision and scale
            precision = int(params[0]) if len(params) > 0 else 10
            scale = int(params[1]) if len(params) > 1 else 2
            
            # Convert to Decimal and round to specified scale, then convert to float for SQLite
            if isinstance(value, (int, float)):
                decimal_value = Decimal(str(value))
                # Create a string representation with the right number of decimal places
                format_str = f"0.{'0' * scale}"
                rounded_decimal = decimal_value.quantize(Decimal(format_str), rounding=ROUND_HALF_UP)
                # Convert back to float for SQLite compatibility
                return float(rounded_decimal)
            return value

        elif base_type in ['varchar', 'char']:
            length = int(params[0]) if len(params) > 0 else 255
            if isinstance(value, str) and len(value) > length:
                return value[:length]
            return str(value) if value is not None else None
    
    base_type = attr_type.lower()
    
    if base_type in ['integer', 'int', 'bigint', 'smallint', 'tinyint']:
        if isinstance(value, float):
            return int(round(value))
        elif isinstance(value, str) and value.replace('.', '').replace('-', '').isdigit():
            return int(float(value))
        return int(value) if value is not None else None
        
    elif base_type in ['decimal', 'numeric']:
        if isinstance(value, (int, float)):
            decimal_value = Decimal(str(value))
            rounded_decimal = decimal_value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            return float(rounded_decimal)
        return value
        
    elif base_type in ['float', 'double', 'real']:
        return float(value) if value is not None else None
        
    elif base_type in ['boolean', 'bool']:
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        return bool(value) if value is not None else None
        
    elif base_type == 'varchar':
        if isinstance(value, str) and len(value) > 255:
            return value[:255]
        return str(value) if value is not None else None
    
    elif base_type == 'char':
        if isinstance(value, str) and len(value) > 1:
            return value[:1]
        return str(value) if value is not None else None
    
    elif base_type in ['text', 'string', 'event_type', 'resource_type']:
        return str(value) if value is not None else None

    elif base_type == 'date':
        if value is None:
            return None
        return _coerce_to_date(value)
    
    elif base_type in ['datetime', 'timestamp']:
        if value is None:
            return None
        return _coerce_to_datetime(value)
    
    elif base_type == 'time':
        if value is None:
            return None
        return _coerce_to_time(value)
    
    # Default: return as-is
    return value


def _coerce_to_date(value: Any) -> Any:
    """Coerce a value to date-only string (YYYY-MM-DD)."""
    from datetime import datetime, date
    
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    
    if isinstance(value, datetime):
        return value.date().isoformat()
    
    if isinstance(value, str):
        try:
            # Handle ISO 8601 strings like '1961-10-11T07:25:55.709Z'
            clean = value.replace('Z', '+00:00')
            dt = datetime.fromisoformat(clean)
            return dt.date().isoformat()
        except (ValueError, TypeError):
            pass
        date_match = re.match(r'(\d{4}-\d{2}-\d{2})', str(value))
        if date_match:
            return date_match.group(1)
    
    return value


def _coerce_to_datetime(value: Any) -> Any:
    """Coerce a value to datetime string (YYYY-MM-DD HH:MM:SS)."""
    from datetime import datetime, date
    
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    
    if isinstance(value, date):
        return f"{value.isoformat()} 00:00:00"
    
    if isinstance(value, str):
        try:
            clean = value.replace('Z', '+00:00')
            dt = datetime.fromisoformat(clean)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            pass
    
    return value


def _coerce_to_time(value: Any) -> Any:
    """Coerce a value to time-only string (HH:MM:SS)."""
    from datetime import datetime, time
    
    if isinstance(value, time):
        return value.strftime('%H:%M:%S')
    
    if isinstance(value, datetime):
        return value.strftime('%H:%M:%S')
    
    if isinstance(value, str):
        try:
            clean = value.replace('Z', '+00:00')
            dt = datetime.fromisoformat(clean)
            return dt.strftime('%H:%M:%S')
        except (ValueError, TypeError):
            pass
        time_match = re.match(r'(\d{2}:\d{2}:\d{2})', str(value))
        if time_match:
            return time_match.group(1)
    
    return value
