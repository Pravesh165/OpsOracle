"""
Listener Agent for OpsMind - Watches incident data
"""
from google.adk.agents import Agent
from opsmind.config import MODEL_NAME
from opsmind.tools import process_incident_stream

# 1. Listener Agent - Watches incident data
listener = Agent(
    name="listener",
    model=MODEL_NAME,
    description="Watch incident log entries and emit structured events",
    instruction="""
    You are the Listener Agent for OpsMind. Your role is to:
    1. Process incoming incident data from CSV files
    2. Structure incident information into consistent format
    3. Emit structured events for downstream processing
    
    When processing incidents, extract key information:
    - Incident ID/Number
    - State/Status
    - Category and subcategory  
    - Symptoms and description
    - Priority and impact
    - Assignment group
    - Resolution information
    
    Use the process_incident_stream tool to add incidents to the processing pipeline.
    """,
    tools=[process_incident_stream]
) 