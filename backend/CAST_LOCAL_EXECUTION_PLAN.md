# InsightGraph CAST-Local Execution Plan

Status date: 2026-03-24
Owner: InsightGraph

## Goal
Transform InsightGraph into a local CAST-like analyzer with:
- deep call trace (resolved method-to-method, N-hop)
- CK quality metrics + hotspot risk
- method usage view
- graph-aware RAG for AI analysis

## Current implementation status

### Sprint 1: Call Resolver + CK metrics
- [x] Added internal call resolver to generate `CALLS_RESOLVED`
- [x] Added N-hop derived relations `CALLS_NHOP`
- [x] Added CK metrics on class nodes:
  - `wmc`
  - `cbo`
  - `rfc`
  - `lcom` (proxy, graph-based)
- [x] Persist relation metadata (`confidence_score`, `resolution_method`, `hop_distance`)

### Sprint 2: Git hotspot
- [x] Added per-file churn extraction from `git log --name-only`
- [x] Added node fields:
  - `git_churn`
  - `hotspot_score` (`complexity * churn`, clamped)
- [x] Added endpoint `GET /api/hotspots`

### Sprint 3: Method usage + RAG
- [x] Added endpoint `GET /api/method/{node_key}/usages`
- [x] Added endpoint `GET /api/rag/search`
- [x] Integrated RAG retrieval in `/api/ask` context composition

### Sprint 4: Advanced UI and scale
- [ ] Migrate graph rendering to 3D for large graphs
- [ ] Add evolution dashboard with hotspot trend and technical debt trend
- [ ] Add persisted embedding index (SQLite/FAISS) for stronger semantic recall

## Definition of done by capability

### Call Resolver
- `CALLS_RESOLVED` appears in memory and Neo4j
- Impact analysis includes `CALLS_RESOLVED` and `CALLS_NHOP`
- Method usage endpoint returns callers/callees with metadata

### CK Metrics
- Class nodes contain `wmc`, `cbo`, `rfc`, `lcom`
- Metrics are recalculated every scan
- Metrics are visible through graph endpoints

### Hotspots
- Nodes include `git_churn` and `hotspot_score`
- `/api/hotspots` returns sorted critical nodes
- Risk prioritization can use hotspot score

### RAG
- `/api/ask` uses graph summary + retrieved relevant nodes
- `/api/rag/search` returns query-relevant nodes

## Next technical steps
1. Validate with real repositories and tune call-resolution scoring.
2. Improve LCOM from proxy to field-sharing based metric when field-level extraction is available in full scan pipeline.
3. Persist semantic index for RAG and add re-ranking.
4. Wire frontend views for Hotspots and Method Usage in UI panels.

