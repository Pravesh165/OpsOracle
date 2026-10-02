# OpsMind - SRE/DevOps Knowledge Repository & Incident Management Assistant

OpsMind is an AI-powered SRE/DevOps knowledge repository and incident management system built with Google's Agent Development Kit (ADK). It serves as a comprehensive knowledge base that can answer any DevOps/SRE question using historical data from incidents, JIRA issues, comments, and changelog. When the knowledge base doesn't have sufficient information, it automatically falls back to web search for current information.

## 🏗️ Architecture

OpsMind uses a **multi-agent system** with integrated safety guardrails:

1. **Root Agent** - SRE/DevOps knowledge repository and main user interface
2. **Knowledge Repository Tools** - Answer questions using comprehensive historical data
3. **Search Agent** - Dedicated Google Search capability for current information fallback
4. **Listener Agent** - Watches incident logs and structures data
5. **Synthesizer Agent** - Uses RAG to analyze incidents with historical context  
6. **Writer Agent** - Generates markdown postmortem documents
7. **Pipeline Agent** - Orchestrates the flow between agents

## 🛡️ Safety & Security Features

OpsMind includes a streamlined safety framework with decorator-based guardrails:

- **@with_guardrail Decorator**: Applied to all user-facing functions for input validation
- **Content Filtering**: UI content escaping and input sanitization
- **Rate Limiting**: Built-in rate limiting to prevent abuse
- **Data Validation**: Comprehensive input validation and output verification
- **Compliance**: Google ADK-compliant safety measures
- **Robust Error Handling**: Graceful handling of malformed data and edge cases

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Google Cloud Project with Vertex AI enabled
- Google Cloud credentials configured

### 1. Installation

```bash
# Install dependencies
pip install -r requirements.txt

```

### 2. Data Setup

**⚠️ Important: Dataset Not Included in Repository**

Due to the large size of the datasets (8GB+ total), they are not included in this repository. You need to download them from Kaggle:

#### Download Required Datasets

1. **Incident Event Log Dataset**
   ```bash
   # Download from Kaggle
   kaggle datasets download shamiulislamshifat/it-incident-log-dataset
   # Extract to: opsmind/data/datasets/incidents/incident_event_log.csv
   ```

2. **Jira Issues Dataset**
   ```bash
   # Download from Kaggle
   kaggle datasets download tedlozzo/apaches-jira-issues
   # Extract to: opsmind/data/datasets/jira/
   # Files: issues.csv, comments.csv, changelog.csv, issuelinks.csv
   ```

#### Dataset Structure

After downloading, your data directory should look like:
```
opsmind/data/datasets/
├── incidents/
│   └── incident_event_log.csv    (44MB - IT incident logs)
└── jira/
    ├── issues.csv                (1.8GB - Jira issue details)
    ├── comments.csv              (3.8GB - Issue comments & discussions)
    ├── changelog.csv             (2.5GB - Field changes & status transitions)
    └── issuelinks.csv            (99MB - Issue relationships & dependencies)
```

### 3. Configuration

Configure your environment variables in `.env` file:

```bash
# Core Configuration
GOOGLE_API_KEY=your_google_api_key
GOOGLE_GENAI_USE_VERTEXAI=FALSE
MODEL=gemini-2.0-flash-001

# Jira Real-time Connector (Optional)
JIRA_ENABLED=FALSE
JIRA_BASE_URL=https://your-company.atlassian.net
JIRA_USERNAME=your-email@company.com
JIRA_API_TOKEN=your_jira_api_token
JIRA_PROJECT_KEYS=PROJ1,PROJ2,PROJ3
JIRA_POLL_INTERVAL=300
```

### 4. Run OpsMind

**Command Line Interface:**
```bash
adk run opsmind
```

**Web Interface:**
```bash
adk web
```

**Validate Configuration:**
```bash
python -c "from opsmind.config import validate_config; validate_config()"
```

## 📊 Data Sources & Analytics

OpsMind leverages multiple data sources for comprehensive incident analysis with robust data loading:

### Static Data Sources (CSV)

1. **Incident Event Log** (44MB)
   - 99 incident records (successfully loaded)
   - Fields: ID, state, category, symptoms, priority, resolution
   - Time range: Real IT environment incident data
   - Use case: Historical incident pattern analysis

2. **Jira Issues Dataset** (1.8GB)
   - 83 Jira issues (successfully loaded with robust parsing)
   - Fields: Summary, description, status, priority, assignee, components
   - Rich metadata: Labels, fix versions, custom fields
   - Use case: Issue resolution patterns and workflows

3. **Jira Comments** (3.8GB)
   - 79 comments (successfully loaded)
   - Discussion threads, resolution notes, updates
   - Author information and timestamps
   - Use case: Communication patterns and solution discovery

4. **Jira Changelog** (2.5GB)
   - 87 changelog entries (successfully loaded)
   - Status transitions, field updates, assignments
   - Historical workflow analysis
   - Use case: Process optimization and bottleneck identification

5. **Jira Issue Links** (99MB)
   - 99 issue links (successfully loaded)
   - Dependencies, relationships, and connections
   - Link types: blocks, relates to, duplicates
   - Use case: Impact analysis and dependency mapping

### Real-time Data Sources (Optional)

- **Live Jira Integration**: Real-time issue updates, comments, and status changes
- **Custom Connectors**: Extensible framework for additional data sources

### Data Processing Features

- **Robust CSV Loading**: Multi-strategy parsing handles malformed CSV files gracefully
- **RAG-powered Analysis**: Semantic search across all data sources
- **Intelligent Filtering**: Context-aware data retrieval
- **Multi-source Correlation**: Links incidents with Jira issues
- **Pattern Recognition**: Identifies recurring issues and solutions
- **Automated Insights**: Generates actionable recommendations
- **Smart Fallback System**: Automatically searches web when knowledge base lacks information

## 🧠 Intelligent Knowledge System

OpsMind operates as a comprehensive knowledge repository with intelligent fallback:

### **Knowledge Base First**
1. **Question Analysis**: Extracts key DevOps/SRE terms from your question
2. **Multi-source Search**: Searches across incidents, JIRA issues, comments, changelog
3. **Evidence Compilation**: Finds relevant historical solutions and patterns
4. **Confidence Assessment**: Evaluates the quality and relevance of found information

### **Web Search Fallback**
When knowledge base information is insufficient (confidence < 30%), OpsMind automatically:
1. **Delegates to Search Agent**: Uses Google's built-in search via dedicated search agent
2. **Current Information**: Finds up-to-date solutions and best practices
3. **Source Verification**: Prioritizes authoritative DevOps/SRE sources
4. **Combined Results**: Merges historical data with current information

### **Example Workflow**
```
User: "How do I troubleshoot Kubernetes pod startup failures?"
↓
1. Knowledge Base Search: Finds 15 historical incidents/issues
2. Confidence Check: High confidence (0.8) - sufficient historical data
3. Response: Historical solutions + patterns from your organization
```

```
User: "What's new in Kubernetes 1.29 networking?"
↓
1. Knowledge Base Search: Finds 2 general networking issues
2. Confidence Check: Low confidence (0.2) - insufficient current data
3. Web Search Fallback: Searches for Kubernetes 1.29 networking updates
4. Response: Combined historical context + current information
```

## 💬 Sample Prompts

Once OpsMind is running, try these prompts:

### Knowledge Repository Queries
```
"Why am I getting 502 errors from my load balancer?"

"How do I troubleshoot high CPU usage in production?"

"What causes database connection timeouts?"

"How to resolve Kubernetes pod crash loops?"

"Find similar issues to: service discovery failing after deployment"

"What are the most common causes of memory leaks?"

"How was this resolved: Redis performance degradation"

"Best practices for deployment rollbacks"
```

### Working Search Examples
```
"Search for JIRA issues that contain 'config'"

"Find comments mentioning 'fixed'"

"Show me changelog entries for status transitions"

"Search the knowledge base for 'browser' issues"

"Find problems related to 'Linux' configuration"
```

### Historical Analysis
```
"Show patterns in critical incidents over the past year"

"What are the most common failure types in our infrastructure?"

"Analyze resolution times for network-related issues"

"Find trends in database performance problems"

"Search knowledge base for Docker configuration issues"
```

### Incident Management
```
"Generate postmortem for incident INC0000045"

"Correlate incident INC0000067 with JIRA activity"

"Show timeline for incident with related changes"

"Find JIRA discussions about specific incidents"
```

## 🔧 Agent Details

### Listener Agent
- **Role**: Process incident streams
- **Input**: CSV incident data
- **Output**: Structured incident events
- **Tools**: `process_incident_stream`

### Synthesizer Agent  
- **Role**: RAG-based incident analysis
- **Input**: Incident events + historical context
- **Output**: Comprehensive summaries
- **Tools**: `get_incident_context`, `create_incident_summary`

### Writer Agent
- **Role**: Generate postmortem documents
- **Input**: Incident summaries
- **Output**: Markdown postmortems
- **Tools**: `generate_postmortem_content`, `save_postmortem`

### Pipeline Agent
- **Role**: Orchestrate agent workflows
- **Input**: User requests
- **Output**: Coordinated agent responses

### Root Agent
- **Role**: Main user interface
- **Input**: User queries
- **Output**: Delegated responses from specialized agents

### Search Agent
- **Role**: Web search capability for fallback
- **Input**: Search queries when knowledge base is insufficient
- **Output**: Current information from web sources

## 📁 Project Structure

```
opsmind/
├── opsmind/                    # Main OpsMind package
│   ├── config/                 # Configuration management
│   │   ├── __init__.py        # Config exports
│   │   └── settings.py        # Environment variables & validation
│   ├── context/               # Context management and retrieval
│   │   ├── __init__.py        # Context exports
│   │   ├── interface.py       # Context interface definitions
│   │   ├── manager.py         # Context management logic
│   │   └── retrieval.py       # RAG context retrieval
│   ├── core/                   # Core agent implementations
│   │   ├── agents/            # Individual agent definitions
│   │   │   ├── __init__.py           # Agent exports
│   │   │   ├── listener.py           # Incident data processing
│   │   │   ├── synthesizer.py        # RAG-based analysis
│   │   │   ├── writer.py             # Postmortem generation
│   │   │   ├── pipeline.py           # Agent orchestration
│   │   │   ├── search.py             # Google search capability
│   │   │   └── root.py               # Main user interface
│   │   ├── safety/            # Safety framework (streamlined)
│   │   │   ├── __init__.py           # Safety exports
│   │   │   └── framework.py          # Core safety framework
│   │   └── __init__.py        # Core exports
│   ├── data/                   # Data management & loading
│   │   ├── connectors/        # Real-time data connectors
│   │   │   ├── __init__.py           # Connector exports
│   │   │   ├── base.py               # Base connector interface
│   │   │   ├── jira.py              # Jira real-time connector
│   │   │   └── manager.py            # Multi-connector management
│   │   ├── datasets/          # Data files (download from Kaggle)
│   │   │   ├── incidents/     # IT incident logs
│   │   │   │   └── incident_event_log.csv
│   │   │   └── jira/          # Jira project data
│   │   │       ├── issues.csv
│   │   │       ├── comments.csv
│   │   │       ├── changelog.csv
│   │   │       └── issuelinks.csv
│   │   ├── __init__.py        # Data exports
│   │   ├── loader.py          # Robust CSV data loading with multiple strategies
│   │   └── manager.py         # Unified data source management
│   ├── tools/                  # Agent tool functions
│   │   ├── __init__.py        # Tool exports
│   │   ├── guardrail.py       # Streamlined guardrail decorators
│   │   ├── incidents.py       # Incident processing tools
│   │   ├── knowledge.py       # Knowledge repository tools
│   │   └── postmortems.py     # Postmortem generation tools
│   ├── utils/                  # Utility functions
│   │   ├── __init__.py        # Utils exports
│   │   ├── gcp_storage.py     # GCP storage utilities
│   │   ├── helpers.py         # Data processing utilities
│   │   └── logging.py         # Logging configuration
│   ├── __init__.py            # Main package entry
│   └── agent.py               # ADK compatibility layer
├── output/                     # Generated postmortems & logs
├── requirements.txt            # Python dependencies
├── pyproject.toml             # Project configuration
├── Makefile                   # Development commands
└── README.md                  # This file
```

## 🧪 Testing

Test the system to verify everything is working:

```bash
# Quick data validation
python -c "
from opsmind.data.loader import load_incident_data, load_jira_data
incidents = load_incident_data()
jira_data = load_jira_data()
print(f'Incidents loaded: {len(incidents)}')
print(f'JIRA issues loaded: {len(jira_data["issues"])}')
print(f'Comments loaded: {len(jira_data["comments"])}')
print(f'Changelog loaded: {len(jira_data["changelog"])}')
"

# Test search functionality
python -c "
import asyncio
from opsmind.tools.knowledge import search_knowledge_base
from google.adk.tools.tool_context import ToolContext

class MockContext:
    def __init__(self):
        self.state = {}

async def test_search():
    context = MockContext()
    result = await search_knowledge_base(context, 'config', limit=3)
    print(f'Search results: {result["total_results"]} items found')

asyncio.run(test_search())
"
```

## 📋 Sample Output

OpsMind generates comprehensive postmortem documents:

```markdown
# Incident Postmortem: INC0000045

## Executive Summary
Database connection failure affecting production services from 01:16 to 11:29.
Analysis based on 127 similar incidents and 45 related Jira issues.

## Incident Details
- **Incident ID**: INC0000045
- **Date/Time**: 29/2/2016 01:16
- **Duration**: ~10 hours  
- **Severity**: Medium Priority
- **Affected Systems**: Production Database

## Root Cause Analysis
Connection timeout due to network configuration changes.
Pattern identified across 12 similar incidents in past 6 months.

## Related Jira Issues
- **INFRA-2341**: Database connectivity issues (Resolved)
- **NET-1156**: Network timeout configurations (In Progress)
- **MON-445**: Database monitoring improvements (Closed)

## Timeline
- 01:16 - Initial incident reported
- 02:30 - Escalated based on similar incident INC0000032
- 08:53 - Issue escalated to database team
- 11:29 - Resolution implemented using JIRA-2341 solution

## Resolution
Network configuration reverted to previous stable state.
Solution adapted from Jira issue INFRA-2341 comments.

## Lessons Learned
Based on analysis of 127 similar incidents:
- Implement automated rollback procedures (mentioned in 23 cases)
- Enhance monitoring (recommended in 67% of similar incidents)
- Update runbooks (action item in 45 related cases)

## Action Items
1. **Database Monitoring** - Implement connection health checks
2. **Automated Failover** - Based on patterns from JIRA-2341, INFRA-1876
3. **Documentation Update** - Consolidate runbooks per MON-445 recommendations
```

## 🔑 Key Features

- **RAG-powered Analysis**: Uses historical incident and Jira data with robust parsing
- **Multi-source Intelligence**: Correlates incidents with Jira issues, comments, and changes
- **Automatic Postmortems**: Generates comprehensive markdown documents
- **Real-time Integration**: Optional live Jira connector for current incidents
- **Pattern Recognition**: Identifies recurring issues and proven solutions
- **Multi-Agent Architecture**: Specialized agents for different tasks
- **Streamlined Safety**: Decorator-based guardrails for input validation
- **Robust Data Loading**: Handles malformed CSV files with multiple parsing strategies
- **Working Search**: Fully functional search across all data sources
- **Extensible Design**: Easy to add new data sources and connectors

## 🔄 Usage Workflow

1. **Data Ingestion**: Robust CSV loading with multiple parsing strategies
2. **Context Retrieval**: RAG system searches across all historical data
3. **Analysis**: Synthesizer Agent correlates incidents with Jira patterns  
4. **Documentation**: Writer Agent creates comprehensive postmortems
5. **Orchestration**: Pipeline Agent coordinates the entire workflow
6. **Interface**: Root Agent provides conversational interaction
7. **Fallback**: Search Agent handles web search when knowledge base is insufficient

## ⚙️ Configuration Options

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `GOOGLE_API_KEY` | Google AI API key | - | ✅ |
| `MODEL` | AI model to use | `gemini-2.0-flash-001` | ❌ |
| `JIRA_ENABLED` | Enable real-time Jira | `FALSE` | ❌ |
| `JIRA_BASE_URL` | Jira instance URL | - | Only if Jira enabled |
| `JIRA_USERNAME` | Jira username | - | Only if Jira enabled |
| `JIRA_API_TOKEN` | Jira API token | - | Only if Jira enabled |
| `JIRA_PROJECT_KEYS` | Projects to monitor | - | Only if Jira enabled |
| `JIRA_POLL_INTERVAL` | Update frequency (seconds) | `300` | ❌ |

### Jira Integration Setup

1. **Generate API Token**: Jira → Account Settings → Security → API tokens
2. **Configure Projects**: Set `JIRA_PROJECT_KEYS` to comma-separated project keys
3. **Test Connection**: Enable with `JIRA_ENABLED=TRUE`

The Jira connector automatically fetches:
- Recently updated issues and status changes
- New comments and discussions  
- Field updates and workflow transitions
- Work logs and time tracking data

## 🚧 Current Status

OpsMind is production-ready with these capabilities:

- ✅ **Multi-agent Architecture** - Specialized agents for different tasks
- ✅ **Robust Data Loading** - Handles malformed CSV files with multiple parsing strategies
- ✅ **Working Search System** - Fully functional search across all data sources
- ✅ **RAG-based Analysis** - Semantic search across loaded data
- ✅ **Jira Integration** - Real-time and historical data processing
- ✅ **Postmortem Generation** - Comprehensive markdown documents
- ✅ **Pattern Recognition** - Identifies trends across incidents and solutions
- ✅ **Streamlined Safety** - Decorator-based guardrails for input validation
- ✅ **Configurable Connectors** - Environment-based configuration
- ✅ **Data Validation** - Ensures data integrity and availability
- ✅ **Web Search Fallback** - Automatic search when knowledge base is insufficient

## 🤝 Contributing

To extend OpsMind:

1. **Add Data Sources**: Implement new connectors in `data/connectors/`
2. **Create Agents**: Add specialized agents in `core/agents/`
3. **Enhance Tools**: Implement new functionality in `tools/`
4. **Improve RAG**: Enhance context retrieval and analysis
5. **Extend Configuration**: Add new environment variables and validation
6. **Add Guardrails**: Extend the decorator-based safety system

## 📚 References & Data Sources

- **Incident Data**: [IT Incident Resolution Dataset](https://www.kaggle.com/datasets/shamiulislamshifat/it-incident-log-dataset)
- **Jira Data**: [Jira Issue Dataset](https://www.kaggle.com/datasets/tedlozzo/apaches-jira-issues)
- **Framework**: [Google Agent Development Kit](https://google.github.io/agent-development-kit/)
- **Architecture**: [ADK Multi-Agent Systems](https://bgiri-gcloud.medium.com/how-to-build-multi-agent-systems-with-adk-agent-development-kit-cd727ab00ba2)

---

**OpsMind** - *From Incident to Insight, Autonomously* 🧠⚡ 