# InsightGraph

**O "Google Maps" da Arquitetura de Software** — Plataforma de análise de impacto e visualização de arquitetura full-stack projetada para rodar 100% localmente.

Suporta análise multi-projeto de codebases **Java (Spring Boot)**, **TypeScript/React**, e **SQL (PL/SQL)** com dois modelos de IA:

| Modelo | Função |
|---|---|
| `qwen3-coder-next:q4_K_M` | Motor de código — scanner e análise SQL |
| `qwen3:8b` | Interface inteligente — Q&A sobre arquitetura |

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| **Python** | 3.11+ | Backend |
| **Node.js** | 18+ | Frontend |
| **Neo4j Desktop** | 5.x | Graph database |
| **Ollama** | Latest | Local AI inference |

### 1. Neo4j Setup

1. Download and install [Neo4j Desktop](https://neo4j.com/download/).
2. Create a new project and database.
3. Set the password to `password` (or change via `NEO4J_PASSWORD` env var).
4. Start the database — it should be accessible at `bolt://localhost:7687`.

### 2. Ollama Setup

```bash
# Install Ollama from https://ollama.com
# Pull both models
ollama pull qwen3-coder-next:q4_K_M
ollama pull qwen3:8b
```

Ensure Ollama is running (`http://localhost:11434`).

> **Note:** SQL parsing requires the coder model. AI Q&A requires the chat model. Java and TypeScript parsing works without Ollama.

---

## Quick Start

### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Start the server
python main.py
# or: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## Usage

1. **Add Workspaces**: Paste project directory paths in the top bar and click **+ Add**.
2. **Scan**: Click **▶ Scan All** to analyze all added workspaces.
3. **Explore**: Navigate the graph, zoom, and pan on the canvas.
4. **Impact Analysis**: Click any node to see its upstream (who calls it) and downstream (what it calls).
5. **Filter**: Use sidebar filters by project and layer (Frontend, API, Service, Database).
6. **Ask AI**: Click **🤖 Ask AI** to open the intelligent Q&A panel and ask questions like:
   - "Quais endpoints usam essa tabela?"
   - "Qual tela chama essa API?"
   - "O que acontece se eu remover essa coluna?"

---

## Architecture

```
Scanner
  ↓
Coder-Next (qwen3-coder-next:q4_K_M)
  ↓
Dependency Extraction
  ↓
Neo4j Graph Database
  ↓
Qwen (qwen3:8b)
  ↓
Analysis & Q&A
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `password` | Neo4j password |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `qwen3-coder-next:q4_K_M` | Coder model for SQL scanning |
| `OLLAMA_CHAT_MODEL` | `qwen3:8b` | Chat model for Q&A |

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/scan` | Start scanning `{ "paths": [...] }` |
| `GET` | `/api/scan/status` | Get scan progress (with %) |
| `GET` | `/api/graph` | Get full graph (`?project=&layer=`) |
| `GET` | `/api/graph/stats` | Get graph statistics |
| `GET` | `/api/impact/{node_key}` | Get upstream/downstream neighbors |
| `GET` | `/api/projects` | List scanned projects |
| `POST` | `/api/ask` | Ask AI `{ "question": "...", "context_node": "..." }` |
| `GET` | `/api/health` | Check service health |
