"""
Logging utilities for OpsMind
"""
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def get_logger(name: str):
    """Get a configured logger instance"""
    return logging.getLogger(name)

# Callback logging for ADK agents
def log_query_to_model(context) -> None:
    """Log the query being sent to the model"""
    logging.info(f"[QUERY TO MODEL] {getattr(context, 'query', 'N/A')}")

def log_model_response(context) -> None:
    """Log the response from the model"""
    logging.info(f"[MODEL RESPONSE] {getattr(context, 'response', 'N/A')}") 