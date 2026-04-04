# 🧠 Second Brain: AI Team Assistant (Railway Edition)

This is the core intelligence of the **Second Brain**. A multi-agent orchestrator designed to operate on **Obsidian** vaults, allowing a team of specialized agents (Manager, Planner, Builder, Researcher, and Critic) to collaborate on the structured creation and editing of notes and code.

🚀 **Live Access**: [https://second-brain-production-53b3.up.railway.app/](https://second-brain-production-53b3.up.railway.app/)

## 🏗️ Decoupled Architecture

This repository is part of a microservices architecture:
1.  **Assistant (This Repo)**: Manages the user interface (Streamlit), task orchestration, and vault persistence.
2.  **[Gemini Proxy Balancer](https://github.com/Abraham2106/gemini-proxy-balancer)**: An independent service that handles API Key rotation and load balancing to mitigate quota limits (429/503).

## ✨ Elite Features

- 🤖 **Professional Multi-Agent Logic**: Coordinated reasoning between specialized agents to solve complex tasks.
- ✒️ **Surgical Editing (Patch System)**: Modify your Obsidian notes using high-precision `unified diff` patches.
- 🗃️ **SQLite Indexing**: Your entire vault (links, tags, and content) is indexed so agents have global context.
- 🐳 **Docker Ready**: Configured for instant deployment on Railway with data persistence.

## 🚀 Deployment and Configuration

To run it locally or in the cloud, you need to configure the following environment variables:

```env
# URL of your Gemini Proxy Balancer instance
GEMINI_PROXY_URL="https://your-proxy.up.railway.app/v1/chat/completions"

# Path to your vault (on Railway use /app/obsidian-vaults)
OBSIDIAN_VAULT_PATH="/app/obsidian-vaults"
```

### Running with Docker
```bash
docker build -t second-brain .
docker run -p 8501:8501 --env-file .env second-brain
```

## 🛠️ Tech Stack
- **UI**: Streamlit
- **Logic**: Python 3.12 (Layered Architecture)
- **Database**: SQLite
- **Infrastructure**: Docker & Railway
