"""
Data helper utilities for OpsMind
"""
import json
import pandas as pd
from typing import Any, Union


def safe_get(data: Union[pd.Series, dict], key: str, default: str = "unknown") -> str:
    """
    Safely get value from pandas Series or dictionary, handling NaN values
    
    Args:
        data: Pandas Series or dictionary
        key: Key to get value for
        default: Default value if key not found or value is NaN
        
    Returns:
        String value or default
    """
    if isinstance(data, pd.Series):
        value = data.get(key, default)
    else:
        value = data.get(key, default)
    
    # Handle various NaN representations
    if value is None or str(value).lower() == 'nan':
        return default
    
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        # If pd.isna fails, continue with the value
        pass
    
    return str(value) if value != default else default


def safe_json_loads(json_data: str) -> Any:
    """
    Safely load JSON data with NaN handling
    
    Args:
        json_data: JSON string to parse
        
    Returns:
        Parsed JSON object with NaN values cleaned
        
    Raises:
        json.JSONDecodeError: If JSON parsing fails
    """
    try:
        # First attempt to load JSON normally
        data = json.loads(json_data)
        
        # Clean any NaN values that might have slipped through
        return clean_nan_values(data)
        
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"JSON decode error: {e}", json_data, 0)


def clean_nan_values(obj: Any) -> Any:
    """
    Recursively clean NaN values from nested data structures
    
    Args:
        obj: Object to clean
        
    Returns:
        Cleaned object with NaN values replaced with "unknown"
    """
    if isinstance(obj, dict):
        return {k: clean_nan_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan_values(v) for v in obj]
    elif obj is None or str(obj).lower() == 'nan':
        return "unknown"
    else:
        try:
            if pd.isna(obj):
                return "unknown"
        except (TypeError, ValueError):
            pass
        return obj


def validate_csv_file(file_path, file_type: str = "data") -> bool:
    """
    Validate that a CSV file exists and is readable
    
    Args:
        file_path: Path to CSV file
        file_type: Type of file for logging
        
    Returns:
        True if file is valid, False otherwise
    """
    from pathlib import Path
    from opsmind.config import logger
    
    try:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"{file_type} file not found: {file_path}")
            return False
        
        if not path.is_file():
            logger.warning(f"{file_type} path is not a file: {file_path}")
            return False
        
        if path.suffix.lower() != '.csv':
            logger.warning(f"{file_type} file is not a CSV: {file_path}")
            return False
        
        # Try to read the first few rows to validate format
        try:
            df = pd.read_csv(path, nrows=1)
            if df.empty:
                logger.warning(f"{file_type} file is empty: {file_path}")
                return False
        except Exception as e:
            logger.warning(f"{file_type} file is not readable: {file_path} - {e}")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error validating {file_type} file {file_path}: {e}")
        return False 