"""
Formula expression evaluator.
Runs parsed formulas using SQL and basic arithmetic/date helpers.
"""

import re
import random
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import text

from .parser import FormulaParser, ParsedExpression

logger = logging.getLogger(__name__)


class FormulaEvaluator:
    """Evaluates formula expressions against a database."""
    
    def __init__(self, session: Session):
        """Create evaluator with a SQLAlchemy session."""
        self.session = session
        self.parser = FormulaParser()
    
    def evaluate(self, expression: str, context: Dict[str, Any]) -> Any:
        logger.debug(f"FORMULA EVAL: Starting evaluation of: {expression}")
        logger.debug(f"FORMULA EVAL: Context: {context}")
        
        try:
            # Parse the expression
            parsed = self.parser.parse(expression)
            logger.debug(f"FORMULA EVAL: Parsed type: {parsed.expression_type}")
            
            # Substitute variables in the expression
            substituted_expr = self._substitute_variables(expression, context)
            logger.debug(f"FORMULA EVAL: After substitution: {substituted_expr}")
            
            # Evaluate based on expression type
            result = None
            # Check for date arithmetic first (e.g., '@created_at + DAYS(RANDOM(20,40))')
            if ' - DAYS(' in substituted_expr or ' + DAYS(' in substituted_expr:
                result = self._evaluate_date_arithmetic_expression(substituted_expr)
            elif parsed.expression_type == 'sql' or substituted_expr.strip().upper().startswith("SELECT"):
                result = self._evaluate_sql_expression(substituted_expr, parsed)
            elif parsed.expression_type == 'table_reference':
                result = self._evaluate_table_reference(substituted_expr, parsed)
            else:
                result = self._evaluate_arithmetic_expression(substituted_expr, parsed)
            
            logger.debug(f"FORMULA EVAL: Final result: {result}")
            return result
                
        except Exception as e:
            logger.error(f"FORMULA EVAL: Error evaluating expression '{expression}': {e}")
            return None
    
    def _substitute_variables(self, expression: str, context: Dict[str, Any]) -> str:
        """Replace @vars in the expression with values from context."""
        def replace_var(match):
            var_name = match.group(1)
            if var_name in context:
                value = context[var_name]
                # Handle different value types
                if isinstance(value, str):
                    return f"'{value}'"
                else:
                    return str(value)
            else:
                logger.warning(f"Variable @{var_name} not found in context")
                return match.group(0)  # Return original if not found
        
        # Replace @variable with actual values
        var_pattern = re.compile(r'@([A-Za-z_][A-Za-z0-9_]*)')
        return var_pattern.sub(replace_var, expression)
    
    def _evaluate_sql_expression(self, expression: str, parsed: ParsedExpression) -> Any:
        """Run a SQL-based expression after substitutions."""
        logger.debug(f"FORMULA EVAL: SQL expression input: {expression}")
        
        # Handle complex expressions with date arithmetic
        if ' - DAYS(' in expression or ' + DAYS(' in expression:
            logger.debug(f"FORMULA EVAL: Detected date arithmetic expression")
            return self._evaluate_date_arithmetic_expression(expression)
        
        # Handle RANDOM functions
        expression = self._process_random_functions(expression)
        logger.debug(f"FORMULA EVAL: After RANDOM processing: {expression}")
        
        # Fix SQLite-specific syntax issues
        original_expr = expression
        expression = self._fix_sqlite_syntax(expression)
        if expression != original_expr:
            logger.debug(f"FORMULA EVAL: After SQLite syntax fix: {expression}")
        
        try:
            # Execute the SQL query
            logger.debug(f"FORMULA EVAL: Executing SQL: {expression}")
            result = self.session.execute(text(expression)).scalar()
            logger.debug(f"FORMULA EVAL: SQL query result: {result} (type: {type(result)})")
            
            if result is None:
                logger.debug(f"FORMULA EVAL: SQL query returned NULL - no matching records")
            
            return result
            
        except Exception as e:
            logger.error(f"FORMULA EVAL: Error executing SQL expression '{expression}': {e}")
            return None
    
    def _evaluate_table_reference(self, expression: str, parsed: ParsedExpression) -> Any:
        """Convert table reference to SQL and evaluate."""
        if parsed.sql_query:
            return self._evaluate_sql_expression(parsed.sql_query, parsed)
        else:
            logger.error(f"Could not convert table reference to SQL: {expression}")
            return None
    
    def _evaluate_arithmetic_expression(self, expression: str, parsed: ParsedExpression) -> Any:
        """Handle plain arithmetic with date/random helpers."""
        # Handle date functions
        expression = self._process_date_functions(expression)
        
        # Handle RANDOM functions
        expression = self._process_random_functions(expression)
        
        try:
            # Use eval for simple arithmetic (with safety checks)
            if self._is_safe_arithmetic(expression):
                return eval(expression)
            else:
                logger.error(f"Unsafe arithmetic expression: {expression}")
                return None
                
        except Exception as e:
            logger.error(f"Error evaluating arithmetic expression '{expression}': {e}")
            return None
    
    def _evaluate_date_arithmetic_expression(self, expression: str) -> Optional[datetime]:
        """Handle expressions like 'subquery - DAYS(30)'."""
        try:
            # Use regex to properly parse DAYS() function calls
            
            # Pattern to match " - DAYS(...)" or " + DAYS(...)" handling nested parentheses
            # This pattern looks for DAYS( and then matches everything until the last )
            days_pattern = re.compile(r'(.+?)\s*([+-])\s*DAYS\s*\((.+)\)$', re.IGNORECASE)
            match = days_pattern.match(expression)
            
            if match:
                sql_part = match.group(1).strip()
                operator = match.group(2)  # '+' or '-'
                days_content = match.group(3).strip()
                
                logger.debug(f"FORMULA EVAL: Parsed date arithmetic: SQL='{sql_part}', op='{operator}', days_content='{days_content}'")
                
                # Process RANDOM functions in the days content
                processed_days = self._process_random_functions(days_content)
                logger.debug(f"FORMULA EVAL: After RANDOM processing: '{processed_days}'")
                days = int(processed_days)
                
                # Execute the SQL part first (or use as literal date)
                sql_part = self._fix_sqlite_syntax(sql_part)
                logger.debug(f"FORMULA EVAL: Executing SQL part: '{sql_part}'")

                # Check if sql_part is a quoted string literal (date value from context)
                stripped = sql_part.strip()
                if (stripped.startswith("'") and stripped.endswith("'")) or \
                   (stripped.startswith('"') and stripped.endswith('"')):
                    base_result = stripped[1:-1]  # Remove quotes
                    logger.debug(f"FORMULA EVAL: Using literal date: {base_result}")
                else:
                    base_result = self.session.execute(text(sql_part)).scalar()
                    logger.debug(f"FORMULA EVAL: SQL result: {base_result}")
                
                if base_result:
                    # Convert to datetime
                    if isinstance(base_result, str):
                        base_date = datetime.fromisoformat(base_result.replace('Z', '+00:00'))
                    else:
                        base_date = base_result
                    
                    # Apply date arithmetic
                    if operator == '-':
                        result_date = base_date - timedelta(days=days)
                        logger.debug(f"FORMULA EVAL: Date arithmetic: {base_result} - {days} days = {result_date}")
                    else:  # operator == '+'
                        result_date = base_date + timedelta(days=days)
                        logger.debug(f"FORMULA EVAL: Date arithmetic: {base_result} + {days} days = {result_date}")
                    
                    return result_date
                else:
                    logger.debug(f"FORMULA EVAL: SQL returned NULL, cannot perform date arithmetic")
                    return None
            
            logger.warning(f"FORMULA EVAL: Could not parse date arithmetic expression: {expression}")
            return None
            
        except Exception as e:
            logger.error(f"Error in date arithmetic expression '{expression}': {e}")
            return None
    
    def _process_date_functions(self, expression: str) -> str:
        """
        Process date functions like DAYS(30), HOURS(2), etc.
        
        Args:
            expression: Expression containing date functions
            
        Returns:
            Expression with date functions converted to SQLite-compatible format
        """
        def replace_date_func(match):
            func = match.group(1).upper()
            value = int(match.group(2))
            
            # SQLite uses datetime() function for date arithmetic
            if func == 'DAYS':
                return f"datetime('now', '-{value} days')"
            elif func == 'HOURS':
                return f"datetime('now', '-{value} hours')"
            elif func == 'MINUTES':
                return f"datetime('now', '-{value} minutes')"
            else:
                return match.group(0)
        
        # Handle subtraction with date functions for SQLite
        # Convert "expression - DAYS(n)" to SQLite datetime arithmetic
        subtract_days_pattern = re.compile(r'([^-\s]+)\s*-\s*DAYS\s*\(\s*(\d+)\s*\)', re.IGNORECASE)
        
        def replace_subtract_days(match):
            base_expr = match.group(1).strip()
            days = int(match.group(2))
            return f"datetime({base_expr}, '-{days} days')"
        
        expression = subtract_days_pattern.sub(replace_subtract_days, expression)
        
        # Handle addition with date functions
        add_days_pattern = re.compile(r'([^+\s]+)\s*\+\s*DAYS\s*\(\s*(\d+)\s*\)', re.IGNORECASE)
        
        def replace_add_days(match):
            base_expr = match.group(1).strip()
            days = int(match.group(2))
            return f"datetime({base_expr}, '+{days} days')"
        
        expression = add_days_pattern.sub(replace_add_days, expression)
        
        # Handle other date functions without arithmetic
        date_pattern = re.compile(r'(DAYS|HOURS|MINUTES)\s*\(\s*(\d+)\s*\)', re.IGNORECASE)
        return date_pattern.sub(replace_date_func, expression)
    
    def _process_random_functions(self, expression: str) -> str:
        """
        Process RANDOM functions like RANDOM(30, 365).
        
        Args:
            expression: Expression containing RANDOM functions
            
        Returns:
            Expression with RANDOM functions evaluated
        """
        def replace_random(match):
            min_val = int(match.group(1))
            max_val = int(match.group(2))
            return str(random.randint(min_val, max_val))
        
        random_pattern = re.compile(r'RANDOM\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)', re.IGNORECASE)
        return random_pattern.sub(replace_random, expression)
    
    def _fix_sqlite_syntax(self, expression: str) -> str:
        """
        Fix SQLite-specific syntax issues in expressions.
        
        Args:
            expression: Expression to fix
            
        Returns:
            Fixed expression compatible with SQLite
        """
        # Fix MIN(SELECT ...) syntax - SQLite needs it as SELECT MIN(...) FROM ... (without outer parentheses)
        min_select_pattern = re.compile(r'MIN\s*\(\s*SELECT\s+([^)]+)\s*\)', re.IGNORECASE)
        
        def fix_min_select(match):
            inner_content = match.group(1)
            # Parse "column FROM table WHERE condition"
            if ' FROM ' in inner_content:
                parts = inner_content.split(' FROM ', 1)
                column_part = parts[0].strip()
                from_where_part = parts[1].strip()
                
                # Parse table name and WHERE clause
                if ' WHERE ' in from_where_part:
                    table_where = from_where_part.split(' WHERE ', 1)
                    table_name = table_where[0].strip()
                    where_clause = table_where[1].strip()
                    return f'SELECT MIN("{column_part}") FROM "{table_name}" WHERE {where_clause}'
                else:
                    return f'SELECT MIN("{column_part}") FROM "{from_where_part}"'
            else:
                return match.group(0)  # Return original if can't parse
        
        expression = min_select_pattern.sub(fix_min_select, expression)
        
        # Fix MAX(SELECT ...) syntax
        max_select_pattern = re.compile(r'MAX\s*\(\s*SELECT\s+([^)]+)\s*\)', re.IGNORECASE)
        
        def fix_max_select(match):
            inner_content = match.group(1)
            if ' FROM ' in inner_content:
                parts = inner_content.split(' FROM ', 1)
                column_part = parts[0].strip()
                from_where_part = parts[1].strip()
                
                # Parse table name and WHERE clause
                if ' WHERE ' in from_where_part:
                    table_where = from_where_part.split(' WHERE ', 1)
                    table_name = table_where[0].strip()
                    where_clause = table_where[1].strip()
                    return f'SELECT MAX("{column_part}") FROM "{table_name}" WHERE {where_clause}'
                else:
                    return f'SELECT MAX("{column_part}") FROM "{from_where_part}"'
            else:
                return match.group(0)
        
        expression = max_select_pattern.sub(fix_max_select, expression)
        
        # Fix AVG(SELECT ...) syntax
        avg_select_pattern = re.compile(r'AVG\s*\(\s*SELECT\s+([^)]+)\s*\)', re.IGNORECASE)
        
        def fix_avg_select(match):
            inner_content = match.group(1)
            if ' FROM ' in inner_content:
                parts = inner_content.split(' FROM ', 1)
                column_part = parts[0].strip()
                from_where_part = parts[1].strip()
                
                # Parse table name and WHERE clause
                if ' WHERE ' in from_where_part:
                    table_where = from_where_part.split(' WHERE ', 1)
                    table_name = table_where[0].strip()
                    where_clause = table_where[1].strip()
                    return f'SELECT AVG("{column_part}") FROM "{table_name}" WHERE {where_clause}'
                else:
                    return f'SELECT AVG("{column_part}") FROM "{from_where_part}"'
            else:
                return match.group(0)
        
        expression = avg_select_pattern.sub(fix_avg_select, expression)
        
        return expression
    
    def _is_safe_arithmetic(self, expression: str) -> bool:
        """
        Check if an arithmetic expression is safe to evaluate.
        
        Args:
            expression: Expression to check
            
        Returns:
            True if safe, False otherwise
        """
        # Only allow numbers, basic operators, and parentheses
        safe_pattern = re.compile(r'^[\d\+\-\*\/\(\)\s\.]+$')
        return bool(safe_pattern.match(expression))
    
    def evaluate_with_date_arithmetic(self, base_date: datetime, expression: str, context: Dict[str, Any]) -> datetime:
        """
        Evaluate an expression that results in a date/datetime.
        
        Args:
            base_date: Base datetime to work from
            expression: Expression to evaluate (e.g., "- DAYS(30)")
            context: Variable context
            
        Returns:
            Calculated datetime
        """
        try:
            # Handle date arithmetic expressions
            expression = self._substitute_variables(expression, context)
            expression = self._process_random_functions(expression)
            
            # Parse date operations
            if '- DAYS(' in expression:
                days_match = re.search(r'- DAYS\((\d+)\)', expression)
                if days_match:
                    days = int(days_match.group(1))
                    return base_date - timedelta(days=days)
            
            elif '+ DAYS(' in expression:
                days_match = re.search(r'\+ DAYS\((\d+)\)', expression)
                if days_match:
                    days = int(days_match.group(1))
                    return base_date + timedelta(days=days)
            
            elif '- HOURS(' in expression:
                hours_match = re.search(r'- HOURS\((\d+)\)', expression)
                if hours_match:
                    hours = int(hours_match.group(1))
                    return base_date - timedelta(hours=hours)
            
            elif '+ HOURS(' in expression:
                hours_match = re.search(r'\+ HOURS\((\d+)\)', expression)
                if hours_match:
                    hours = int(hours_match.group(1))
                    return base_date + timedelta(hours=hours)
            
            # If no date arithmetic found, return base date
            return base_date
            
        except Exception as e:
            logger.error(f"Error in date arithmetic: {e}")
            return base_date
