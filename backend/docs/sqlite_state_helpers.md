# SQLite State Helpers

## Persistência de scan
- `state_store.persist_scan_status(payload)` grava o estado completo do scan na tabela `app_state` sob a chave `scan_status`.
- `state_store.load_scan_status()` recupera o último registro para restaurar progresso após reinícios ou crashes.

## Tabela `codeql_jobs`
- Persiste `job_id`, `project_id`, `suite`, `status`, `details_json`, `created_at` e `updated_at`.
- Índices para projeto e status aceleram listagens e dashboards.
- `state_store.upsert_codeql_job(...)` é chamado no início e término de cada análise para manter histórico durável.
- `state_store.list_codeql_jobs(...)`/`get_codeql_job` expõem o histórico e permitem retomar ou inspecionar jobs longos (~34 min).

## Saved views / Knowledge Layer
- O `GraphCanvas` agora expõe um handle (`captureViewState`, `applyViewState`) que captura posições de nós e o viewport atual para salvar/recuperar views.
- O botão "Saved Views" abre um painel com listagem, refresh e formulário. Ele usa `/api/views` (SQLite) para criar views com filters + `reactflow_state` JSON.
- Ao carregar uma view, aplicamos filtros, projeto selecionado (quando único) e restauramos posições/viewport com o handle do canvas, sem recalcular o layout completo.

## Anotações por nó
- `NodeDetail` carrega anotações para o nó (`/api/annotations?node_key=...`), renderiza title/conteúdo/severity/tag e mantém um formulário rápido.
- Tags persistem via `/api/tags`; a UI permite reutilizar tags existentes e marcações com cor.
- Ao criar uma anotação nova, o backend grava tudo em SQLite (tabela `annotations`) e a lista é atualizada em seguida.

## Próximos passos sugeridos
1. Expor filtros mais ricos nas views (por exemplo, saved filters de `searchTerm` ou camadas específicas) e persistir trechos do canvas (zoom/pan) no web storage.
2. Oferecer histórico de anotações (cronologia) e exportável para relatórios PDF.
3. Integrar as views salvas ao dashboard (por exemplo, "carregar view crítica" dentro da parte de knowledge layer) e registrar o último autor/contexto.
