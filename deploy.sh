#!/bin/bash

# OpsMind ADK Deployment Script
# Simple deployment using ADK's built-in commands

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
PROJECT_ID=""
WITH_UI=true
MAKE_PUBLIC=false
FORCE_REBUILD=false

# Print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Usage function
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy OpsMind using ADK's built-in deployment commands

OPTIONS:
    -p, --project-id PROJECT_ID    GCP Project ID (required)
    --no-ui                        Deploy without web UI (API only)
    --public                       Make service publicly accessible
    -f, --force                    Force rebuild
    -h, --help                     Show this help message

EXAMPLES:
    $0 -p my-project-id
    $0 -p my-project-id --public
    $0 -p my-project-id --no-ui --force

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--project-id)
            PROJECT_ID="$2"
            shift 2
            ;;
        --no-ui)
            WITH_UI=false
            shift
            ;;
        --public)
            MAKE_PUBLIC=true
            shift
            ;;
        -f|--force)
            FORCE_REBUILD=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate required parameters
if [[ -z "$PROJECT_ID" ]]; then
    print_error "Project ID is required. Use -p or --project-id"
    usage
    exit 1
fi

# Check dependencies
check_dependencies() {
    print_status "Checking dependencies..."
    
    local missing_tools=()
    
    if ! command -v gcloud &> /dev/null; then
        missing_tools+=("gcloud")
    fi
    
    if ! command -v adk &> /dev/null; then
        missing_tools+=("adk")
    fi
    
    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        print_error "Missing required tools: ${missing_tools[*]}"
        print_error "Please install them and try again"
        exit 1
    fi
    
    print_success "All dependencies are installed"
}

# Authenticate with GCP
authenticate_gcp() {
    print_status "Authenticating with GCP..."
    
    # Check if already authenticated
    if gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q "@"; then
        print_success "Already authenticated with GCP"
    else
        print_status "Please authenticate with GCP..."
        gcloud auth login
    fi
    
    # Set project
    gcloud config set project "$PROJECT_ID"
    print_success "Project set to: $PROJECT_ID"
}

# Enable required APIs
enable_apis() {
    print_status "Enabling required APIs..."
    
    local apis=(
        "run.googleapis.com"
        "containerregistry.googleapis.com"
        "cloudbuild.googleapis.com"
    )
    
    for api in "${apis[@]}"; do
        print_status "Enabling $api..."
        gcloud services enable "$api" --project="$PROJECT_ID"
    done
    
    print_success "Required APIs enabled"
}

# Check environment configuration
check_env() {
    print_status "Checking environment configuration..."
    
    if [[ ! -f ".env" ]]; then
        print_warning ".env file not found. Creating from template..."
        if [[ -f "env.template" ]]; then
            cp env.template .env
            print_warning "Please edit .env file with your API keys before deployment"
            read -p "Press Enter to continue after editing .env file..."
        else
            print_error "No .env or env.template file found"
            exit 1
        fi
    fi
    
    # Check for required environment variables
    if ! grep -q "GOOGLE_API_KEY" .env || grep -q "your_google_api_key_here" .env; then
        print_warning "Please set your GOOGLE_API_KEY in .env file"
        read -p "Press Enter to continue after setting API key..."
    fi
    
    print_success "Environment configuration checked"
}

# Deploy using ADK
deploy_with_adk() {
    print_status "Deploying OpsMind using ADK..."
    
    local deploy_cmd="adk deploy cloud_run"
    
    # Add UI flag if requested
    if [[ "$WITH_UI" == "true" ]]; then
        deploy_cmd="$deploy_cmd --with_ui"
    fi
    
    # Add force flag if requested
    if [[ "$FORCE_REBUILD" == "true" ]]; then
        deploy_cmd="$deploy_cmd --force"
    fi
    
    # Add the agent name
    deploy_cmd="$deploy_cmd opsmind"
    
    print_status "Running: $deploy_cmd"
    
    # Execute deployment
    eval "$deploy_cmd"
    
    print_success "Deployment completed!"
}

# Make service public if requested
make_public() {
    if [[ "$MAKE_PUBLIC" != "true" ]]; then
        return 0
    fi
    
    print_status "Making service publicly accessible..."
    
    # Get service name from gcloud (assumes it follows ADK naming convention)
    local service_name=$(gcloud run services list --filter="metadata.name:opsmind" --format="value(metadata.name)" --limit=1)
    
    if [[ -z "$service_name" ]]; then
        print_warning "Could not find service name. Please make it public manually:"
        print_status "gcloud run services add-iam-policy-binding SERVICE_NAME --region=REGION --member=\"allUsers\" --role=\"roles/run.invoker\""
        return 0
    fi
    
    # Get region
    local region=$(gcloud config get-value run/region 2>/dev/null || echo "us-central1")
    
    # Make service public
    gcloud run services add-iam-policy-binding "$service_name" \
        --region="$region" \
        --member="allUsers" \
        --role="roles/run.invoker"
    
    print_success "Service is now publicly accessible"
}

# Get service URL
get_service_url() {
    print_status "Getting service URL..."
    
    local service_name=$(gcloud run services list --filter="metadata.name:opsmind" --format="value(metadata.name)" --limit=1)
    
    if [[ -n "$service_name" ]]; then
        local region=$(gcloud config get-value run/region 2>/dev/null || echo "us-central1")
        local service_url=$(gcloud run services describe "$service_name" --region="$region" --format="value(status.url)")
        
        if [[ -n "$service_url" ]]; then
            print_success "Service URL: $service_url"
        fi
    fi
}

# Main deployment function
main() {
    print_status "Starting ADK deployment for OpsMind..."
    print_status "Project: $PROJECT_ID"
    print_status "With UI: $WITH_UI"
    print_status "Make Public: $MAKE_PUBLIC"
    print_status "Force Rebuild: $FORCE_REBUILD"
    echo
    
    check_dependencies
    authenticate_gcp
    enable_apis
    check_env
    deploy_with_adk
    make_public
    get_service_url
    
    print_success "🚀 OpsMind deployment complete!"
    print_status "Your AI agent is now running on Google Cloud Run"
    
    if [[ "$WITH_UI" == "true" ]]; then
        print_status "Access the web interface at the URL shown above"
    fi
    
    print_status "To view logs: gcloud run services logs tail opsmind-service"
    print_status "To redeploy: $0 -p $PROJECT_ID"
}

# Run main function
main "$@" 