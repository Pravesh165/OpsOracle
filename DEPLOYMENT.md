# OpsMind - ADK Deployment

Deploy your OpsMind AI agent to Google Cloud Run in minutes using ADK's built-in deployment commands, as shown in [this tutorial](https://timtech4u.medium.com/building-and-deploying-ai-agents-in-minutes-with-googles-adk-part-1-abbf2ed43486).

## 🚀 Quick Start

### 1. Setup Environment

```bash
# Copy environment template
cp env.template .env

# Edit with your Google API key
nano .env
```

### 2. Authenticate with GCP

```bash
# Login to Google Cloud
gcloud auth login

# Set your project
gcloud config set project YOUR_PROJECT_ID
```

### 3. Deploy with ADK

```bash
# Simple deployment with web UI
./deploy.sh -p YOUR_PROJECT_ID

# Or deploy and make public
./deploy.sh -p YOUR_PROJECT_ID --public

# Or deploy without UI (API only)
./deploy.sh -p YOUR_PROJECT_ID --no-ui
```

That's it! 🎉 Your OpsMind agent is now live on Google Cloud Run.

## 📱 Usage Examples

### Web Interface
Visit the URL provided after deployment to access the chat interface.

### CLI Mode (Local)
```bash
# Run locally in CLI mode
adk run opsmind

# Run locally with web UI
adk web opsmind
```

### API Calls
```bash
# Test your deployed service
curl -X POST "https://your-service-url/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Process recent incidents"}'
```

## 🔧 Advanced Options

### Custom Deployment
```bash
# Manual ADK deployment
adk deploy cloud_run --with_ui opsmind

# Deploy with custom resources
adk deploy cloud_run --with_ui opsmind --cpu 2 --memory 4Gi

# Force rebuild
adk deploy cloud_run --with_ui opsmind --force
```

### Make Service Public
```bash
# Get service name
gcloud run services list

# Make it public
gcloud run services add-iam-policy-binding SERVICE_NAME \
  --region=REGION \
  --member="allUsers" \
  --role="roles/run.invoker"
```

## 📊 Monitoring

```bash
# View logs
gcloud run services logs tail opsmind-service

# Check service status
gcloud run services describe opsmind-service --region=us-central1
```

## 🔄 Updates

```bash
# Redeploy after changes
./deploy.sh -p YOUR_PROJECT_ID -f
```

## 💡 Why ADK Deployment?

As shown in the [Medium tutorial](https://timtech4u.medium.com/building-and-deploying-ai-agents-in-minutes-with-googles-adk-part-1-abbf2ed43486), ADK provides:

- ✅ **Automatic containerization** - No need to write Dockerfiles
- ✅ **Built-in Cloud Run integration** - Handles all GCP configuration
- ✅ **Web UI included** - Chat interface out of the box
- ✅ **Zero configuration** - Works with minimal setup
- ✅ **Fast deployment** - Deploy in minutes, not hours

## 🛠️ Troubleshooting

### Common Issues

1. **ADK not found**: Install with `pip install google-adk`
2. **Authentication error**: Run `gcloud auth login` 
3. **Project not set**: Run `gcloud config set project YOUR_PROJECT_ID`
4. **API not enabled**: Script will enable required APIs automatically

### Debug Mode

```bash
# Enable debug logging
export DEBUG=true

# Run with verbose output
./deploy.sh -p YOUR_PROJECT_ID --force
```

---

**Original Tutorial**: [Building and Deploying AI Agents in Minutes with Google's ADK](https://timtech4u.medium.com/building-and-deploying-ai-agents-in-minutes-with-googles-adk-part-1-abbf2ed43486)

This approach leverages ADK's built-in capabilities for the fastest and most reliable deployment experience. 