# InsightGraph

InsightGraph é uma suíte local de inteligência de software que combina:

- **Parser/CodeQL** (análise de código Java/TypeScript/SQL via Tree‑Sitter e CodeQL).  
- **Grafo Neo4j** (dependências e contexto técnico).  
- **RAG/embeddings** (SQLite + `rag_store.db` + `rag_index.json`).  
- **Frontend Vite + React** (visualização do grafo, dashboards, simulações e painel “Perguntar à IA”).  
- **IA com Ollama** (modelos rápidos, chat, complexos e embeddings respondendo perguntas contextualizadas).

## Visão geral da arquitetura

| Camada | O que faz |
| --- | --- |
| Backend | `backend/main.py`: FastAPI + scanner “scan_project” + semantic + impacto + integração Ollama + CLI (`scan`, `serve`, `regression`). |
| Frontend | `frontend/`: Vite + React + Tailwind com canvas de grafo, painel de IA, modais de análise, simulações e inventário API. |
| IA | Ollama local (`qwen2.5`, `qwen3.5`, `qwen3-coder-next`, `nomic-embed-text`) alimentando `/api/ask`, embeddings e parsing SQL. |
| Persistência | Neo4j (grafo), SQLite (`insightgraph_state.db`), RAG (`rag_store.db`, `rag_index.json`). |

## Pré-requisitos

1. **Sistema Operating:** Windows/macOS/Linux (scripts no diretório `scripts/` para PowerShell; tudo usa bibliotecas cross-platform).  
2. **Python 3.11+** (3.12.x recomendado).  
3. **Node.js 20+** (Vite + React 19).  
4. **Neo4j 5.x** rodando em `bolt://localhost:7687` (usuário `neo4j` / senha `password` por padrão).  
5. **Ollama** acessível via `http://localhost:11434`.  
6. **RAM**: 16 GB+ (modelos Ollama ocupam de 4 a 16+ GB de disco/VRAM).  
7. **Ferramentas recomendadas:** Git, curl, VS Code (opcional, mas facilita inspeção).

## Passo a passo de instalação

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate          # Unix/macOS: source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

- Crie um `.env` ao lado de `backend/main.py` para sobrescrever padrões (`NEO4J_URI`, `OLLAMA_*`, `PROJECT_NAME`, etc.).  
- Execute em modo desenvolvimento:
  ```powershell
  python main.py serve
  ```
  ou
  ```powershell
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
  ```
  A API estará disponível em `http://localhost:8000/api/...`.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

- O Vite serve em `http://localhost:5173` e proxya `/api` para o backend.  
- Build de produção: `npm run build` (saída em `frontend/dist`).

### Neo4j & estado local

- Inicie o Neo4j (Docker ou Desktop):
  ```powershell
  docker run --rm -p 7474:7474 -p 7687:7687 --env NEO4J_AUTH=neo4j/password neo4j:5
  ```
- InsightGraph mantém:
  * `backend/insightgraph_state.db` (estado + views + anotações).  
  * `backend/rag_store.db` (embeddings).  
  * `backend/rag_index.json` (índice de nós RAG).
- Para limpar o estado: `./scripts/reset-insightgraph-state.ps1` (pronto para rodar no PowerShell).  
- O índice RAG é reconstruído automaticamente ao rodar um novo `scan`.

## Modelos Ollama recomendados

| Variável | Uso | Modelo padrão | Tamanho estimado (disco/VRAM) | Instalar |
| --- | --- | --- | --- | --- |
| `OLLAMA_FAST_MODEL` | Resumos rápidos e fallback do scanner | `qwen2.5-coder:1.5b` | ≈4 GB | `ollama install qwen2.5-coder:1.5b` |
| `OLLAMA_CHAT_MODEL` | Principal Q&A/Ask Panel | `qwen3.5:4b` | ≈10–12 GB | `ollama install qwen3.5:4b` |
| `OLLAMA_COMPLEX_MODEL` | Relatórios complexos / regressão | `qwen3-coder-next:q4_K_M` | ≈16 GB | `ollama install qwen3-coder-next:q4_K_M` |
| `OLLAMA_SMALL_MODEL` | Último fallback do pipeline | `qwen2.5-coder:7b` | ≈13–15 GB | `ollama install qwen2.5-coder:7b` |
| `OLLAMA_EMBED_MODEL` | Embeddings / semantic search | `nomic-embed-text` | ≈0.5 GB | `ollama install nomic-embed-text` |

- Instale o Ollama seguindo https://ollama.com/docs/installation e confirme com `ollama list`.  
- Se o servidor Ollama não estiver local, configure `OLLAMA_URL=http://host:11434`.  
- Para GPU: `OLLAMA_FORCE_GPU=1` e `OLLAMA_NUM_GPU=<número>`.  
- O backend tenta os modelos em cascata (chat → fast → small), então mantenha todos instalados.  
- Verifique saúde via `GET /api/health` e `/api/rag/status`.

## Fluxos comuns

1. **Scan completo:**  
   ```powershell
   python backend/main.py scan --path "C:\caminho\do\projeto"
   ```
   Use `--fail-on-risk 30` para pipelines falharem em risco alto.  
2. **Execução de regressão:** `python backend/main.py regression`.  
3. **Reset de estado local:** `scripts/reset-insightgraph-state.ps1`.  
4. **Logs úteis:** observe mensagens como `All AI models failed` ou warnings do Neo4j.  
5. **Painel “AI Assistant”**: aciona `POST /api/ask`, que combina contexto Neo4j + RAG antes de chamar o Ollama.

## Internals de escaneamento

- `scan_project(path)` (em `backend/main.py`) varre arquivos `.java`, `.ts`, `.tsx`, `.sql`, `.prc`, `.fnc`, `.pkg` usando Tree-Sitter e Ollama.  
- Os dados são truncados para Neo4j via `py2neo`, criando nós/relacionamentos com labels como `API_Endpoint`, `Java_Method`, `SQL_Table`.  
- A memória em runtime mantém a lista de nós (`memory_nodes`, `memory_edges`, `rag_index`).  
- Endpoints úteis que o frontend usa:
  * `POST /api/graph/paths`  
  * `GET /api/impact/{nodeKey}`  
  * `GET /api/antipatterns`  
  * `POST /api/ask` / `/simulate` / `/rag/search`

## Configuração adicional & boas práticas

- `.env` recomendado com variáveis como `NEO4J_URI`, `OLLAMA_CHAT_MODEL`, `PROJECT_NAME`.  
- Se a instância Neo4j estiver lenta, aumente o cache de página (p.ex. 4 GB) ou reduza diretórios escaneados retirando entradas de `SKIP_DIRS`.  
- RAG e embeddings ocupam espaço; delete `backend/rag_store.db` somente se for reconstruir (use o reset script).  
- Após mudanças significativas no código, rode `python main.py scan --path ...` para atualizar o índice RAG.  
- Verifique `/api/health` e `/api/rag/status` para garantir que backend, Ollama e embeddings estão prontos.

## Solução de problemas

- **Neo4j não conecta:** confirme com `docker ps` ou Neo4j Desktop e use `bolt://localhost:7687` / `neo4j/password`.  
- **Ollama offline ou falta de modelo:** execute `ollama serve` e reinstale os modelos do README (`ollama list`).  
- **“Falha na busca semântica” no frontend:** aguarde o scan terminar ou reinicie o backend (recarrega `rag_index.json`).  
- **Assistente responde contexto errado:** confira os logs `No JSON found` ou `All AI models failed` e garanta que os nós relevantes estejam indexados.  
- **Preciso limpar views/anotações:** rode o script `scripts/reset-insightgraph-state.ps1` e reinicie o backend para recriar arquivos SQLite/RAG.

## Próximos passos sugeridos

1. Rode `python backend/main.py scan --path path/to/application` para popular o grafo.  
2. Abra o frontend em `http://localhost:5173` (ou `http://localhost:8000` se quiser servir o build backend).  
3. Clique em **“AI Assistant”** e pergunte “O que acontece se eu adicionar ...” após garantir que os modelos estejam carregados.

Para CI/CD: adicione `python backend/main.py scan` ao pipeline, use `--fail-on-risk` como gate e mantenha os arquivos `rag_*` em cache para evitar reembeddings completos.
