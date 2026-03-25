# Plano CAST v2 (Alinhado ao Código Atual)

Data: 2026-03-24

## 1) Estado atual (já implementado)
- Call resolver incremental no scan:
  - `CALLS_RESOLVED` com `confidence_score` e `resolution_method`
  - `CALLS_NHOP` com `hop_distance`
- CK básico por classe:
  - `wmc`, `cbo`, `rfc`, `lcom` (proxy estrutural)
- Hotspot:
  - `git_churn` por arquivo
  - `hotspot_score` por nó
- Endpoints ativos:
  - `/api/impact/analyze`
  - `/api/dataflow/{node_key}`
  - `/api/contracts/broken`
  - `/api/fields/{node_key}`
  - `/api/fragility/{node_key}`
  - `/api/fragility/ranking`
  - `/api/taint/propagate`
  - `/api/symbol/resolve`
  - `/api/side-effects/detect`
  - `/api/bidirectional/analyze`
  - `/api/security/node/{node_key}/vulnerabilities`
  - `/api/method/{node_key}/usages`
  - `/api/hotspots`
  - `/api/rag/search`
  - `/api/rag/index`
  - `/api/graph/search`
  - `/api/metrics/ck`

## 2) Lacunas principais (para fechar “CAST local”)
- Resolver de chamadas:
  - aumentar precisão para chamadas encadeadas e overload
  - melhorar ligação cross-file/cross-module por assinatura
- CK:
  - evoluir `lcom` para cálculo por compartilhamento de campos
  - adicionar `dit` e `noc` reais (hierarquia)
- Git risco:
  - incluir `co-change` (arquivos que quebram juntos)
  - incluir janela temporal configurável (`days`)
- RAG:
  - hoje lexical em memória
  - evoluir para embeddings persistidos (SQLite/FAISS) + rerank
- Frontend:
  - painel dedicado de method usage
  - seção de hotspots no dashboard
  - busca semântica integrada na UI
  - migração para grafo 3D em volume alto

## 3) Plano de execução prático

### Sprint A (backend precisão, 3-5 dias)
1. Refinar call resolver para assinatura de método.
2. Adicionar `dit`/`noc` no scan.
3. Adicionar endpoint de `hotspots?days=...` com filtro temporal.
4. Testes de regressão para scan e impacto.

### Sprint B (RAG robusto, 3-4 dias)
1. Persistir embeddings de nós (nomic-embed-text) em SQLite.
2. Rebuild incremental de índice após scan.
3. `/api/graph/search` híbrido (BM25 + vetor).
4. Ajustar `/api/ask` para priorização híbrida.

### Sprint C (frontend operacional, 4-6 dias)
1. `MethodUsageView` com navegação para caller/callee.
2. Dashboard com tabela de hotspots (filtro por projeto).
3. Busca semântica no topo com highlight no grafo.
4. Troca para grafo 3D em datasets grandes.

## 4) Critérios de pronto
- Impacto usa `CALLS_RESOLVED` e `CALLS_NHOP` em produção.
- CK endpoint retorna risco consistente por projeto.
- Hotspots ordenam corretamente os top arquivos críticos.
- Perguntas em `/api/ask` melhoram recall com contexto relevante.
- UI exibe usos de método e hotspots sem chamadas quebradas.



Simulate: simula mudanças arquiteturais (remoção/adição de nós/arestas), calcula risco e impacto antes de mexer no código real.

Dashboard: abre painel de métricas e risco (hotspots, co-change, evolução, precisão do call graph, status RAG, antipatterns).

CodeQL: abre módulo de segurança estática com projetos/jobs/resultados CodeQL.

AI Assistant: abre chat da IA local para perguntas sobre arquitetura, impacto e recomendações.

Hybrid Search: faz busca no grafo combinando lexical + semântica (embeddings), retornando nós mais relevantes.

Semantic ON: liga/desliga o componente semântico da busca (ON = híbrida; OFF = mais lexical).

Reindex RAG: reconstrói o índice RAG local (incluindo embeddings) para melhorar qualidade das respostas e buscas após mudanças/scan.