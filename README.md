<div align="center">

# 🧠 Second Brain

**AI-Powered Multi-Agent Orchestrator for Obsidian Knowledge Management**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Railway-blueviolet?style=for-the-badge&logo=railway&logoColor=white)](https://second-brain-production-53b3.up.railway.app/)
[![Documentation](https://img.shields.io/badge/Docs-Mintlify-0D9373?style=for-the-badge&logo=readthedocs&logoColor=white)](https://na-dbda1d2b.mintlify.app/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](./Dockerfile)

<br/>

*A team of specialized AI agents that reason, plan, research, build, and critique — working together to create and manage structured knowledge inside your Obsidian vault.*

</div>

---

## Overview

Second Brain is a **multi-agent AI system** that turns natural language instructions into structured Obsidian notes, code files, and knowledge graphs. Instead of a single LLM call, your request flows through a coordinated pipeline of agents, each with a distinct role:

| Agent | Role |
|-------|------|
| **🎯 Manager** | Decomposes the user's request and coordinates the team |
| **📐 Planner** | Designs the file structure, folder hierarchy, and note relationships |
| **🔬 Researcher** | Gathers context from indexed vault content and external sources |
| **🔨 Builder** | Generates the actual Markdown, code, and Obsidian-native formatting |
| **🔍 Critic** | Reviews output quality, consistency, and adherence to instructions |

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Streamlit UI (Chat)                    │
├──────────────────────────────────────────────────────────┤
│                  Application Layer                        │
│  ┌─────────────┐  ┌──────────┐  ┌─────────────────────┐ │
│  │ Orchestrator │──│  Agents  │──│  Persona / Modes    │ │
│  └──────┬──────┘  └──────────┘  └─────────────────────┘ │
├─────────┼────────────────────────────────────────────────┤
│         │           Infrastructure Layer                  │
│  ┌──────▼──────┐  ┌──────────┐  ┌─────────────────────┐ │
│  │   Executor  │  │  SQLite  │  │   Vault Manager     │ │
│  │ (Patch/Write)│  │  (Index) │  │ (Sync/Links/Tags)  │ │
│  └─────────────┘  └──────────┘  └─────────────────────┘ │
├──────────────────────────────────────────────────────────┤
│              Gemini Proxy Balancer (External)             │
│          github.com/Abraham2106/gemini-proxy-balancer     │
└──────────────────────────────────────────────────────────┘
```

## Key Features

- **🤖 Multi-Agent Pipeline** — Five specialized agents collaborate through a structured reasoning chain, not just a single prompt-response cycle.
- **✒️ Surgical File Editing** — Modifies existing notes using `unified diff` patches with SHA-256 integrity checks and full audit logging.
- **🗃️ Deep Vault Indexing** — SQLite indexes every note, wikilink, and tag in your vault, giving agents full structural awareness.
- **🎭 Persona Modes** — Switch between Education, Research, Planning, and Organization modes to adjust agent behavior and output depth.
- **📎 File Attachments** — Upload PDFs and text files as additional context for agent reasoning.
- **🔌 Decoupled Proxy** — All LLM calls route through the [Gemini Proxy Balancer](https://github.com/Abraham2106/gemini-proxy-balancer), keeping API keys secure and enabling intelligent rate-limit handling.

## Quick Start

### Local Development

```bash
# 1. Clone and install
git clone https://github.com/Abraham2106/second-brain.git
cd second-brain
python -m venv venv && venv\Scripts\activate   # Windows
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your GEMINI_PROXY_URL and OBSIDIAN_VAULT_PATH

# 3. Launch
streamlit run src/interfaces/streamlit/ui.py
```

### Docker

```bash
docker build -t second-brain .
docker run -p 8501:8501 --env-file .env \
  -v ./obsidian-vaults:/app/obsidian-vaults \
  second-brain
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_PROXY_URL` | ✅ | Full URL of your proxy endpoint (e.g. `https://your-proxy.up.railway.app/v1/chat/completions`) |
| `OBSIDIAN_VAULT_PATH` | ✅ | Absolute path to your Obsidian vault directory |
| `GEMINI_MODELS` | ❌ | Comma-separated list of model names to use (defaults provided) |

## Tech Stack

| Layer | Technology |
|-------|------------|
| **UI** | Streamlit |
| **Backend** | Python 3.12 (Layered Architecture) |
| **Database** | SQLite (vault index + audit log) |
| **LLM Gateway** | [Gemini Proxy Balancer](https://github.com/Abraham2106/gemini-proxy-balancer) |
| **Hosting** | Docker · Railway |

## Documentation

📖 Full documentation is available at **[na-dbda1d2b.mintlify.app](https://na-dbda1d2b.mintlify.app/)**

## License

MIT © [Abraham Solano](https://github.com/Abraham2106)
