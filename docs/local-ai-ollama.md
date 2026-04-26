# Local AI (Ollama) configuration

InsightGraph on `Testes4D` is local-first.
All main AI flows use the same Ollama runtime layer (`backend/ollama_runtime.py`).

## Required environment variables

- `OLLAMA_URL` (default: `http://localhost:11434`)
- `OLLAMA_FAST_MODEL` (default: `qwen2.5-coder:1.5b`)
- `OLLAMA_CHAT_MODEL` (default: `qwen3.5:4b`)
- `OLLAMA_COMPLEX_MODEL` (default: `qwen3-coder-next:q4_K_M`)
- `OLLAMA_EMBED_MODEL` (default: `nomic-embed-text`)
- `OLLAMA_SMALL_MODEL` (default: `qwen2.5-coder:7b`)

## Model usage by task

- Fast scan / lightweight generation: `OLLAMA_FAST_MODEL`
- AskPanel / conversational graph Q&A: `OLLAMA_CHAT_MODEL`
- Deep analysis / refactor guidance / semantic impact: `OLLAMA_COMPLEX_MODEL`
- Embeddings / RAG indexing: `OLLAMA_EMBED_MODEL`
- Local fallback for chat chain: `OLLAMA_SMALL_MODEL`

## Runtime behavior

- Shared retries and timeout mapping in `OllamaRuntime`
- Friendly local error messages for:
  - connection refused
  - timeout
  - HTTP errors (model missing, OOM, etc.)
- `/api/chat` automatically falls back to `/api/generate` when unsupported by Ollama build

## Recommended model install

```bash
ollama pull qwen2.5-coder:1.5b
ollama pull qwen3.5:4b
ollama pull qwen3-coder-next:q4_K_M
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text
```
