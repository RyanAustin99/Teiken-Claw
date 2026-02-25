"""
Argument validation for tool execution.

This module provides validation and coercion utilities for tool arguments,
ensuring they match the expected schema before execution.

Key Features:
    - Schema-based argument validation
    - Type coercion for common types
    - Safe default value generation
"""

from typing import Any, Dict, List, Optional, Union
import logging

from app.tools.base import Tool

logger = logging.getLogger(__name__)


def validate_tool_args(tool: Tool, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and coerce tool arguments against the tool's schema.
    
    Args:
        tool: Tool instance with json_schema
        args: Raw arguments from Ollama
        
    Returns:
        Validated and coerced arguments dictionary
        
    Raises:
        ValueError: If arguments are invalid and cannot be coerced
    """
    schema = tool.json_schema
    function_def = schema.get("function", {})
    parameters = function_def.get("parameters", {})
    properties = parameters.get("properties", {})
    required = parameters.get("required", [])
    
    validated = {}
    errors = []
    
    # Check required parameters
    for req in required:
        if req not in args:
            errors.append(f"Missing required parameter: {req}")
    
    if errors:
        raise ValueError("; ".join(errors))
    
    # Validate and coerce each argument
    for key, value in args.items():
        if key not in properties:
            # Unknown parameter - allow but warn
            logger.debug(
                f"Unknown parameter '{key}' for tool {tool.name}",
                extra={"tool_name": tool.name, "param": key}
            )
            validated[key] = value
            continue
        
        prop_schema = properties[key]
        try:
            validated[key] = coerce_value(value, prop_schema, key)
        except ValueError as e:
            errors.append(str(e))
    
    if errors:
        raise ValueError("; ".join(errors))
    
    # Fill in defaults for missing optional parameters
    for key, prop_schema in properties.items():
        if key not in validated and "default" in prop_schema:
            validated[key] = prop_schema["default"]
    
    return validated


def coerce_value(
    value: Any,
    schema: Dict[str, Any],
    name: str = "value",
) -> Any:
    """
    Coerce a value to match the expected schema type.
    
    Args:
        value: The value to coerce
        schema: JSON schema for the expected type
        name: Parameter name for error messages
        
    Returns:
        Coerced value
        
    Raises:
        ValueError: If value cannot be coerced
    """
    expected_type = schema.get("type")
    
    if expected_type is None:
        # No type constraint
        return value
    
    # Handle null values
    if value is None:
        if schema.get("nullable", False) or "null" in (expected_type if isinstance(expected_type, list) else []):
            return None
        raise ValueError(f"{name} cannot be null")
    
    # Handle union types
    if isinstance(expected_type, list):
        for t in expected_type:
            if t == "null":
                continue
            try:
                return _coerce_to_type(value, t, schema, name)
            except ValueError:
                continue
        raise ValueError(f"{name} must be one of types: {expected_type}")
    
    return _coerce_to_type(value, expected_type, schema, name)


def _coerce_to_type(
    value: Any,
    expected_type: str,
    schema: Dict[str, Any],
    name: str,
) -> Any:
    """
    Coerce a value to a specific type.
    
    Args:
        value: The value to coerce
        expected_type: The target type string
        schema: Full schema for additional constraints
        name: Parameter name for error messages
        
    Returns:
        Coerced value
        
    Raises:
        ValueError: If coercion fails
    """
    if expected_type == "string":
        return _coerce_string(value, schema, name)
    elif expected_type == "integer":
        return _coerce_integer(value, schema, name)
    elif expected_type == "number":
        return _coerce_number(value, schema, name)
    elif expected_type == "boolean":
        return _coerce_boolean(value, name)
    elif expected_type == "array":
        return _coerce_array(value, schema, name)
    elif expected_type == "object":
        return _coerce_object(value, schema, name)
    else:
        # Unknown type - pass through
        return value


def _coerce_string(value: Any, schema: Dict[str, Any], name: str) -> str:
    """Coerce value to string."""
    if isinstance(value, str):
        result = value
    elif isinstance(value, (int, float, bool)):
        result = str(value)
    else:
        raise ValueError(f"{name} must be a string")
    
    # Check constraints
    min_length = schema.get("minLength")
    max_length = schema.get("maxLength")
    pattern = schema.get("pattern")
    enum_values = schema.get("enum")
    
    if min_length is not None and len(result) < min_length:
        raise ValueError(f"{name} must be at least {min_length} characters")
    
    if max_length is not None and len(result) > max_length:
        raise ValueError(f"{name} must be at most {max_length} characters")
    
    if enum_values is not None and result not in enum_values:
        raise ValueError(f"{name} must be one of: {enum_values}")
    
    return result


def _coerce_integer(value: Any, schema: Dict[str, Any], name: str) -> int:
    """Coerce value to integer."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer, not boolean")
    
    if isinstance(value, int):
        result = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{name} must be an integer")
        result = int(value)
    elif isinstance(value, str):
        try:
            result = int(value)
        except ValueError:
            raise ValueError(f"{name} must be an integer")
    else:
        raise ValueError(f"{name} must be an integer")
    
    # Check constraints
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    
    if maximum is not None and result > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    
    return result


def _coerce_number(value: Any, schema: Dict[str, Any], name: str) -> Union[int, float]:
    """Coerce value to number (int or float)."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number, not boolean")
    
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        try:
            result = float(value)
        except ValueError:
            raise ValueError(f"{name} must be a number")
    else:
        raise ValueError(f"{name} must be a number")
    
    # Check constraints
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    
    if maximum is not None and result > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    
    # Return int if it's a whole number
    if result.is_integer():
        return int(result)
    return result


def _coerce_boolean(value: Any, name: str) -> bool:
    """Coerce value to boolean."""
    if isinstance(value, bool):
        return value
    elif isinstance(value, str):
        lower = value.lower()
        if lower in ("true", "1", "yes", "on"):
            return True
        elif lower in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"{name} must be a boolean")
    elif isinstance(value, (int, float)):
        return bool(value)
    else:
        raise ValueError(f"{name} must be a boolean")


def _coerce_array(value: Any, schema: Dict[str, Any], name: str) -> List[Any]:
    """Coerce value to array."""
    if isinstance(value, list):
        result = value
    elif isinstance(value, str):
        # Try to parse as JSON array
        import json
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                result = parsed
            else:
                raise ValueError(f"{name} must be an array")
        except json.JSONDecodeError:
            raise ValueError(f"{name} must be an array")
    else:
        raise ValueError(f"{name} must be an array")
    
    # Check constraints
    min_items = schema.get("minItems")
    max_items = schema.get("maxItems")
    items_schema = schema.get("items")
    
    if min_items is not None and len(result) < min_items:
        raise ValueError(f"{name} must have at least {min_items} items")
    
    if max_items is not None and len(result) > max_items:
        raise ValueError(f"{name} must have at most {max_items} items")
    
    # Validate items if schema provided
    if items_schema is not None:
        coerced_items = []
        for i, item in enumerate(result):
            coerced_items.append(coerce_value(item, items_schema, f"{name}[{i}]"))
        result = coerced_items
    
    return result


def _coerce_object(value: Any, schema: Dict[str, Any], name: str) -> Dict[str, Any]:
    """Coerce value to object."""
    if isinstance(value, dict):
        result = value
    elif isinstance(value, str):
        # Try to parse as JSON object
        import json
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                result = parsed
            else:
                raise ValueError(f"{name} must be an object")
        except json.JSONDecodeError:
            raise ValueError(f"{name} must be an object")
    else:
        raise ValueError(f"{name} must be an object")
    
    # Check constraints
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    
    for req in required:
        if req not in result:
            raise ValueError(f"{name} missing required property: {req}")
    
    # Validate properties if schema provided
    if properties:
        coerced = {}
        for key, val in result.items():
            if key in properties:
                coerced[key] = coerce_value(val, properties[key], f"{name}.{key}")
            else:
                coerced[key] = val
        result = coerced
    
    return result


def safe_defaults(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate safe default values for a schema.
    
    Args:
        schema: JSON schema for an object
        
    Returns:
        Dictionary with default values for all properties
    """
    properties = schema.get("properties", {})
    defaults = {}
    
    for key, prop_schema in properties.items():
        if "default" in prop_schema:
            defaults[key] = prop_schema["default"]
        else:
            defaults[key] = _get_type_default(prop_schema.get("type", "string"))
    
    return defaults


def _get_type_default(type_str: str) -> Any:
    """Get a safe default value for a type."""
    if type_str == "string":
        return ""
    elif type_str == "integer":
        return 0
    elif type_str == "number":
        return 0.0
    elif type_str == "boolean":
        return False
    elif type_str == "array":
        return []
    elif type_str == "object":
        return {}
    else:
        return None


__all__ = [
    "validate_tool_args",
    "coerce_value",
    "safe_defaults",
]
