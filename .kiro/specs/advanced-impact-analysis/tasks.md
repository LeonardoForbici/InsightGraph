# Implementation Plan: Advanced Impact Analysis

## Overview

Implementação incremental da feature Advanced Impact Analysis para o InsightGraph. As tarefas seguem a ordem de dependência: parsers de campo → motor de impacto → detecção de contrato → rastreamento de fluxo → análise semântica → endpoints REST → frontend. Cada etapa integra ao código existente sem substituir parsers ou endpoints já funcionais.

## Tasks

- [x] 1. Criar módulo `backend/deep_parser.py` com DeepParser para Java
  - [x] 1.1 Implementar `DeepParser.extract_java_field_nodes()` usando tree-sitter
    - Extrair parâmetros de métodos: nome, tipo, modificadores, anotações Spring (`@PathVariable`, `@RequestParam`, `@RequestBody`)
    - Extrair campos de classe: nome, tipo, modificadores, anotações JPA (`@Column`, `@Id`, `@ManyToOne`, `@OneToMany`, `@JoinColumn`)
    - Criar dicts com schema `Field_Level_Node`: `namespace_key`, `name`, `kind`, `data_type`, `parent_key`, `column_name` (snake_case fallback)
    - Retornar `(list[dict], list[dict])` — nós e relacionamentos (`HAS_PARAMETER`, `HAS_FIELD`)
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 1.2 Escrever property test para extração de Field_Level_Nodes Java
    - **Property 1: Field_Level_Nodes extraídos corretamente pelo Deep_Parser Java**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
    - Arquivo: `backend/tests/test_deep_parser.py`
    - Usar `@given(java_class_with_annotations())` com Hypothesis, `max_examples=100`
    - Verificar: `kind` em `VALID_KINDS`, `parent_key` presente, `column_name` em snake_case quando `name` ausente

  - [x] 1.3 Implementar `DeepParser.compute_signature_hash()`
    - SHA-256 de `(nome_método + tipos_parâmetros_ordenados + tipo_retorno)` como string concatenada
    - Retornar hex string de 64 caracteres
    - _Requirements: 1.5, 2.8_

  - [ ]* 1.4 Escrever property test para Signature_Hash
    - **Property 2: Signature_Hash é determinístico e único por assinatura**
    - **Validates: Requirements 1.5, 2.8**
    - Arquivo: `backend/tests/test_deep_parser.py`
    - Verificar: mesmo input → mesmo hash; assinaturas distintas → hashes distintos; `len(hash) == 64`

- [x] 2. Estender `DeepParser` com suporte a Angular/TypeScript
  - [x] 2.1 Implementar `DeepParser.extract_angular_bindings()` usando tree-sitter
    - Detectar decorators `@Component`, `@Injectable`, `@Directive`, `@Pipe` → atributo `angular_type`
    - Extrair propriedades `@Input()` / `@Output()` → `kind = "input_binding"` / `"output_binding"`, relacionamento `HAS_BINDING`
    - Extrair parâmetros do construtor → `kind = "injected_dependency"`, atributo `dependency_type`
    - Extrair chamadas `HttpClient.get/post/put/delete` → relacionamento `CALLS_HTTP` com `http_method` e `url_pattern`
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 2.2 Escrever property test para Angular bindings
    - **Property 5: Angular_Component extrai bindings e injeções corretamente**
    - **Validates: Requirements 3.1, 3.2, 3.3**
    - Arquivo: `backend/tests/test_deep_parser.py`
    - Verificar: `kind` correto para cada tipo de binding; relacionamento `HAS_BINDING` presente

- [x] 3. Expandir `parse_sql_with_ollama()` em `backend/main.py` com prompt avançado
  - [x] 3.1 Substituir o prompt existente por prompt expandido que solicita explicitamente:
    - Parâmetros com modo IN/OUT/IN OUT e tipo de dado
    - Colunas por statement DML (SELECT → `READS_COLUMN`, INSERT/UPDATE/DELETE → `WRITES_COLUMN`)
    - Chamadas entre procedures
    - Procedures individuais de packages com relacionamento `BELONGS_TO_PACKAGE`
    - Calcular `signature_hash` via `DeepParser.compute_signature_hash()` para cada procedure
    - Criar Field_Level_Nodes com `kind = "procedure_param"` e `kind = "column_reference"`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 2.7, 2.8_

  - [ ]* 3.2 Escrever property test para Ollama_SQL_Parser — parâmetros e colunas DML
    - **Property 3: Ollama_SQL_Parser extrai parâmetros e colunas DML com relacionamentos corretos**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
    - Arquivo: `backend/tests/test_sql_parser.py`
    - Usar respostas JSON mockadas com Hypothesis; verificar `param_mode` em `{IN, OUT, IN OUT}` e relacionamentos corretos

  - [ ]* 3.3 Escrever property test para packages PL/SQL
    - **Property 4: Package PL/SQL gera nós individuais por procedure**
    - **Validates: Requirements 2.7**
    - Arquivo: `backend/tests/test_sql_parser.py`
    - Verificar: N procedures no package → N nós `SQL_Procedure` + N relacionamentos `BELONGS_TO_PACKAGE`

- [x] 4. Integrar DeepParser nos parsers existentes de `backend/main.py`
  - [x] 4.1 Expandir `parse_java()` para chamar `DeepParser.extract_java_field_nodes()` após o parsing AST existente
    - Persistir Field_Level_Nodes via `neo4j_service.merge_node()` com label `Field_Level_Node`
    - Persistir relacionamentos `HAS_PARAMETER` e `HAS_FIELD` via `neo4j_service.merge_relationship()`
    - Armazenar em `memory_nodes` / `memory_edges` quando Neo4j indisponível
    - Calcular e armazenar `signature_hash` em cada método Java
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 10.2, 10.3, 10.4_

  - [x] 4.2 Expandir `parse_typescript()` para chamar `DeepParser.extract_angular_bindings()` após o parsing AST existente
    - Mesma lógica de persistência Neo4j / memória
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 10.2, 10.3, 10.4_

  - [x] 4.3 Adicionar índices Neo4j para `Field_Level_Node` em `ensure_indexes()` de `Neo4jService`
    - Índices em: `namespace_key`, `kind`, `data_type`, `parent_key`
    - Labels adicionais: `Parameter`, `Column`, `Input_Binding`, `Output_Binding`, `Injected_Dependency`
    - _Requirements: 10.1_

- [x] 5. Checkpoint — Verificar parsers e persistência
  - Garantir que todos os testes de parsers passam. Verificar que Field_Level_Nodes são criados corretamente no grafo em memória para um arquivo Java e um arquivo TypeScript de exemplo. Perguntar ao usuário se há dúvidas antes de continuar.

- [x] 6. Criar módulo `backend/contract_break_detector.py`
  - [x] 6.1 Implementar `ContractBreakDetector.check_and_mark()`
    - Comparar `current_hash` com `signature_hash` armazenado no nó (Neo4j ou `memory_nodes`)
    - Se diferente: atualizar `contract_broken = True`, salvar `previous_signature_hash`, retornar `True`
    - Confidence_Score de quebras detectadas via hash: >= 95
    - _Requirements: 6.1, 6.5, 10.5_

  - [x] 6.2 Implementar `ContractBreakDetector.get_all_broken()`
    - Query Neo4j: `MATCH (n:Entity) WHERE n.contract_broken = true RETURN n`
    - Fallback memória: filtrar `memory_nodes` por `contract_broken == True`
    - _Requirements: 6.3_

  - [ ]* 6.3 Escrever property test para detecção de contract_broken
    - **Property 8: Detecção de contract_broken via Signature_Hash com Confidence_Score >= 95**
    - **Validates: Requirements 6.1, 6.5**
    - Arquivo: `backend/tests/test_deep_parser.py`
    - Verificar: hash diferente → `contract_broken = True`; hash igual → sem marcação; score >= 95

- [x] 7. Criar módulo `backend/impact_engine.py` com ImpactEngine
  - [x] 7.1 Implementar `ImpactEngine._bfs_impact()` — BFS no grafo de dependências
    - Percorrer relacionamentos relevantes por tipo de mudança (`HAS_PARAMETER`, `CALLS`, `READS_COLUMN`, `WRITES_COLUMN`, `HAS_BINDING`, `CALLS_HTTP`)
    - Respeitar `max_depth` (padrão 5) e limite de 50.000 nós visitados
    - Retornar lista de `AffectedItem` com `call_chain` completa desde `target_key`
    - Suporte a Neo4j (Cypher BFS) e fallback em memória (BFS sobre `memory_edges`)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 4.8_

  - [x] 7.2 Implementar `ImpactEngine._compute_confidence()`
    - `"exact_key"` → 100; `"qualified_name"` → 70–99; `"heuristic"` → 40–69; `"semantic"` → < 40
    - Classificar cada item em `DIRECT`, `TRANSITIVE` ou `INFERRED`
    - Marcar `requires_manual_review = True` quando score < 40
    - _Requirements: 4.6, 4.7, 11.1, 11.2, 11.3, 11.4, 11.6_

  - [x] 7.3 Implementar `ImpactEngine.analyze()` — orquestrador principal
    - Aceitar `ChangeDescriptor` com `change_type` em `{rename_parameter, change_column_type, change_method_signature, change_procedure_param}`
    - Montar `AffectedSet` com `AnalysisMetadata` (`total_affected`, `high_confidence_count`, `low_confidence_count`, `parse_errors`, `unresolved_links`)
    - Adicionar flag `truncated = True` em `analysis_metadata` quando limite de nós atingido
    - _Requirements: 4.1–4.8, 11.5_

  - [ ]* 7.4 Escrever property test para ImpactEngine — Call_Chain completa
    - **Property 6: Impact_Engine retorna Affected_Set completo com Call_Chain para qualquer Change_Descriptor**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4**
    - Arquivo: `backend/tests/test_impact_engine.py`
    - Usar `@given(impact_graph(), change_descriptor())` com Hypothesis
    - Verificar: `call_chain[0] == change.target_key`; `len(call_chain) >= 1` para cada item

  - [ ]* 7.5 Escrever property test para Confidence_Score
    - **Property 7: Confidence_Score está na faixa correta para cada tipo de dependência**
    - **Validates: Requirements 4.6, 11.1, 11.2, 11.3, 11.4**
    - Arquivo: `backend/tests/test_impact_engine.py`
    - Verificar faixas por método de resolução conforme design

  - [ ]* 7.6 Escrever property test para MERGE sem duplicatas
    - **Property 9: MERGE garante ausência de duplicatas em rescans**
    - **Validates: Requirements 10.3**
    - Arquivo: `backend/tests/test_impact_engine.py`
    - Simular N rescans sobre `memory_nodes`; verificar `len(keys) == len(set(keys))`

- [x] 8. Criar módulo `backend/data_flow_tracker.py` com DataFlowTracker
  - [x] 8.1 Implementar `DataFlowTracker.trace_column_to_frontend()`
    - Percorrer cadeia: `Coluna → Entidade (MAPS_TO_COLUMN) → DTO (MAPPED_FROM) → Endpoint (SERIALIZED_BY) → Componente (DISPLAYED_BY)`
    - Retornar `DataFlowChain` com lista de `DataFlowLink` (`from_key`, `to_key`, `rel_type`, `resolved`)
    - Elos não resolvidos marcados com `resolved = False` sem interromper a cadeia
    - Suporte a Neo4j e fallback em memória
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ]* 8.2 Escrever property test para DataFlowTracker
    - **Property 10: Data_Flow_Tracker retorna cadeia completa ou parcial com elos marcados**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6**
    - Arquivo: `backend/tests/test_data_flow.py`
    - Verificar: `len(resolved) >= 1`; elos não resolvidos não interrompem retorno; `chain.links is not None`

- [x] 9. Criar módulo `backend/semantic_analyzer.py` com SemanticAnalyzer
  - [x] 9.1 Implementar `SemanticAnalyzer.analyze_impact()` — integração com qwen3-coder-next
    - Montar prompt com `ChangeDescriptor`, `AffectedSet` e snippets de código dos itens `DIRECT` (máx. 8.000 tokens)
    - Solicitar JSON com campos: `summary`, `risk_level`, `breaking_changes`, `migration_steps`, `estimated_effort`
    - Validar presença de todos os campos; reenviar prompt com instrução de correção até 2 tentativas adicionais
    - Usar exclusivamente `OLLAMA_COMPLEX_MODEL` (`qwen3-coder-next:q4_K_M`)
    - Em caso de erro/timeout: retornar `None` com flag `semantic_analysis_available = False`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 9.2 Escrever property test para SemanticAnalyzer — validação de JSON e reenvio
    - **Property 11: Semantic_Analyzer valida JSON e reenvia prompt em caso de campos ausentes**
    - **Validates: Requirements 8.2, 8.3**
    - Arquivo: `backend/tests/test_semantic_analyzer.py`
    - Mockar respostas do Ollama com campos ausentes; verificar que reenvio ocorre até 2 vezes; verificar que retorna `None` após 3 falhas

- [x] 10. Checkpoint — Verificar módulos de backend
  - Garantir que todos os testes de backend passam (`pytest backend/tests/ -v`). Verificar que `ImpactEngine.analyze()` retorna resultado correto para um grafo em memória simples. Perguntar ao usuário se há dúvidas antes de continuar.

- [x] 11. Adicionar 4 endpoints REST ao `backend/main.py`
  - [x] 11.1 Implementar `POST /api/impact/analyze`
    - Aceitar `ChangeDescriptor` (Pydantic model) no corpo da requisição
    - Validar `change_type` em tipos suportados; retornar HTTP 422 com mensagem descritiva para campos inválidos
    - Chamar `ImpactEngine.analyze()` → `SemanticAnalyzer.analyze_impact()` (se disponível)
    - Retornar `AffectedSet` + `semantic_analysis` (ou `null`) + `analysis_metadata`
    - Tempo de resposta < 15s para grafos até 50.000 nós
    - _Requirements: 9.1, 9.5, 9.6_

  - [x] 11.2 Implementar `GET /api/impact/data-flow/{node_key}`
    - Chamar `DataFlowTracker.trace_column_to_frontend(node_key)`
    - Retornar `DataFlowChain` serializada como JSON
    - _Requirements: 9.2_

  - [x] 11.3 Implementar `GET /api/impact/contract-breaks`
    - Chamar `ContractBreakDetector.get_all_broken()`
    - Para cada artefato com `contract_broken = True`, incluir `affected_set` pré-calculado
    - _Requirements: 9.3, 6.3_

  - [x] 11.4 Implementar `GET /api/impact/field-nodes/{node_key}`
    - Query Neo4j: `MATCH (n:Entity {namespace_key: $key})-[:HAS_PARAMETER|HAS_FIELD|HAS_BINDING]->(f:Field_Level_Node) RETURN f`
    - Fallback memória: filtrar `memory_nodes` por `parent_key == node_key`
    - _Requirements: 9.4_

- [x] 12. Criar `frontend/src/components/ImpactAnalysisPanel.tsx`
  - [x] 12.1 Implementar estrutura do painel com props `{ nodeKey, nodeName, onClose, onHighlightNodes }`
    - Painel lateral com seções: "Analisar Mudança", "Fluxo de Dados", "Quebras de Contrato", "Field Nodes"
    - Formulário para `ChangeDescriptor`: select de `change_type`, input de `parameter_name`, `old_type`, `new_type`, slider de `max_depth`
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 12.2 Implementar chamada a `POST /api/impact/analyze` e exibição do `AffectedSet`
    - Exibir lista de artefatos impactados com badge de categoria (`DIRECT`, `TRANSITIVE`, `INFERRED`), `confidence_score` e `call_chain` expansível
    - Chamar `onHighlightNodes` com os `namespace_key` dos itens do `AffectedSet` para destacar no grafo
    - Exibir `analysis_metadata` (total, high/low confidence, erros)
    - Exibir `semantic_analysis` (summary, risk_level, breaking_changes, migration_steps, estimated_effort) quando disponível
    - _Requirements: 4.5, 4.6, 4.7, 8.1, 8.2, 11.5, 11.6_

  - [x] 12.3 Implementar aba "Fluxo de Dados" com chamada a `GET /api/impact/data-flow/{nodeKey}`
    - Exibir cadeia `Coluna → Entidade → DTO → Endpoint → Componente` como lista linear
    - Elos `resolved = false` exibidos com indicador visual de "não resolvido"
    - _Requirements: 7.5, 7.6_

  - [x] 12.4 Implementar aba "Field Nodes" com chamada a `GET /api/impact/field-nodes/{nodeKey}`
    - Exibir tabela com `name`, `kind`, `data_type`, `param_mode` (quando aplicável)
    - _Requirements: 9.4_

- [x] 13. Adicionar funções de API em `frontend/src/api.ts`
  - Adicionar tipos TypeScript: `ChangeDescriptor`, `AffectedItem`, `AffectedSet`, `DataFlowChain`, `DataFlowLink`, `FieldLevelNode`, `SemanticAnalysis`
  - Adicionar funções: `analyzeImpact()`, `fetchDataFlow()`, `fetchContractBreaks()`, `fetchFieldNodes()`
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 14. Integrar `ImpactAnalysisPanel` em `NodeDetail.tsx` e `App.tsx`
  - [x] 14.1 Adicionar botão "🔍 Analisar Impacto" na aba "Detalhes" do `NodeDetail.tsx`
    - Ao clicar, emitir evento para `App.tsx` abrir o `ImpactAnalysisPanel` com `nodeKey` e `nodeName`
    - Adicionar prop `onOpenImpactAnalysis?: (nodeKey: string, nodeName: string) => void` ao `NodeDetailProps`
    - _Requirements: 9.1_

  - [x] 14.2 Adicionar estado e renderização do `ImpactAnalysisPanel` em `App.tsx`
    - Estado: `impactPanelOpen`, `impactNodeKey`, `impactNodeName`
    - Handler `handleOpenImpactAnalysis` que seta o estado e abre o painel
    - Renderizar `<ImpactAnalysisPanel>` condicionalmente, passando `onHighlightNodes={setAiHighlightedNodes}`
    - _Requirements: 9.1_

- [x] 15. Checkpoint final — Garantir que todos os testes passam
  - Executar `pytest backend/tests/ -v` e verificar que todos os testes passam.
  - Verificar que os 4 endpoints respondem corretamente com dados de exemplo.
  - Verificar que o `ImpactAnalysisPanel` abre e exibe resultados no frontend.
  - Perguntar ao usuário se há dúvidas antes de encerrar.

## Notes

- Tarefas marcadas com `*` são opcionais e podem ser puladas para MVP mais rápido
- Cada tarefa referencia requisitos específicos para rastreabilidade
- Checkpoints garantem validação incremental antes de avançar para a próxima camada
- Property tests usam Hypothesis (Python) com `max_examples=100`
- Todos os novos componentes verificam `neo4j_service.is_connected` antes de queries Cypher
- O `ImpactEngine` nunca é chamado durante o scan — apenas via endpoints REST
