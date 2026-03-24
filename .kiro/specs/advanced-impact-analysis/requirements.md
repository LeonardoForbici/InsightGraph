# Requirements Document

## Introduction

O InsightGraph precisa evoluir de uma ferramenta de visualização de arquitetura para um analisador de código crítico e preciso, equivalente ao CAST Imaging. A feature **Advanced Impact Analysis** eleva a precisão da análise estática para o nível de campo/parâmetro/coluna, tornando a análise de impacto de mudanças confiável o suficiente para decisões de produção.

O sistema já possui parsing via tree-sitter para Java e TypeScript, Neo4j como grafo de dependências, e integração com Ollama (qwen3-coder-next:q4_K_M). Esta feature expande e aprofunda essas capacidades para as três linguagens-alvo: **Java**, **PL/SQL** e **Angular (TypeScript/Angular)**.

---

## Glossary

- **Advanced_Impact_Analyzer**: O subsistema responsável por toda análise de impacto de mudanças de nível avançado.
- **Deep_Parser**: Componente de parsing estático que extrai metadados em nível de campo, parâmetro, tipo e anotação.
- **Impact_Engine**: Motor de cálculo de impacto que percorre o grafo de dependências para determinar o conjunto de artefatos afetados por uma mudança.
- **Change_Descriptor**: Estrutura de dados que descreve uma mudança proposta (ex: renomear parâmetro, alterar tipo de coluna, modificar assinatura de método).
- **Affected_Set**: Conjunto de artefatos (classes, métodos, procedures, componentes Angular, colunas) impactados por um Change_Descriptor.
- **Namespace_Key**: Identificador único de um artefato no grafo, no formato `projeto:caminho_relativo:artefato`.
- **Call_Chain**: Sequência ordenada de chamadas entre artefatos que conecta a origem da mudança ao artefato afetado.
- **PL/SQL_Procedure**: Procedure, function, package body ou trigger definido em PL/SQL.
- **Angular_Component**: Componente, serviço, diretiva ou pipe Angular definido em TypeScript.
- **Field_Level_Node**: Nó no grafo representando um campo de classe, propriedade de interface, parâmetro de método ou coluna de tabela.
- **Signature_Hash**: Hash SHA-256 da assinatura de um artefato (nome + parâmetros + tipos de retorno), usado para detectar mudanças de contrato.
- **Confidence_Score**: Pontuação de 0 a 100 indicando a certeza do Impact_Engine sobre um impacto detectado.
- **qwen3-coder-next**: Modelo Ollama `qwen3-coder-next:q4_K_M`, motor principal de análise semântica.
- **Tree_Sitter_Parser**: Parser AST baseado em tree-sitter, usado para Java e TypeScript/Angular.
- **Ollama_SQL_Parser**: Parser baseado em qwen3-coder-next para PL/SQL, com prompt estruturado e validação de JSON.

---

## Requirements

### Requirement 1: Deep Parsing de Java em Nível de Campo e Parâmetro

**User Story:** Como arquiteto de software, quero que o sistema extraia campos, parâmetros, tipos de retorno e anotações de cada método e classe Java, para que a análise de impacto opere em nível de contrato e não apenas em nível de classe.

#### Acceptance Criteria

1. WHEN o Deep_Parser processa um arquivo `.java`, THE Deep_Parser SHALL extrair para cada método: nome, lista de parâmetros (nome + tipo), tipo de retorno, modificadores de acesso e anotações Spring (`@RequestMapping`, `@PathVariable`, `@RequestBody`, `@RequestParam`).
2. WHEN o Deep_Parser processa um arquivo `.java`, THE Deep_Parser SHALL extrair para cada campo de classe: nome, tipo, modificadores e anotações JPA (`@Column`, `@Id`, `@ManyToOne`, `@OneToMany`, `@JoinColumn`).
3. WHEN o Deep_Parser extrai um parâmetro anotado com `@PathVariable` ou `@RequestParam`, THE Deep_Parser SHALL criar um Field_Level_Node com `kind = "path_variable"` ou `kind = "request_param"` e vinculá-lo ao método via relacionamento `HAS_PARAMETER`.
4. WHEN o Deep_Parser extrai um campo anotado com `@Column`, THE Deep_Parser SHALL registrar o atributo `column_name` no Field_Level_Node com o valor do atributo `name` da anotação, ou o nome do campo em snake_case quando o atributo `name` não estiver presente.
5. THE Deep_Parser SHALL calcular e armazenar o Signature_Hash de cada método Java como SHA-256 de `(nome_método + tipos_parâmetros_ordenados + tipo_retorno)`.
6. IF o Deep_Parser encontrar um arquivo `.java` com erro de sintaxe, THEN THE Deep_Parser SHALL registrar o erro com o caminho do arquivo e número de linha, e continuar o processamento dos demais arquivos sem interromper o scan.
7. THE Deep_Parser SHALL processar arquivos Java usando exclusivamente o Tree_Sitter_Parser, sem depender do qwen3-coder-next para extração estrutural de Java.

---

### Requirement 2: Deep Parsing de PL/SQL em Nível de Parâmetro e Coluna

**User Story:** Como DBA ou desenvolvedor backend, quero que o sistema extraia parâmetros de procedures PL/SQL, colunas lidas/escritas por cada statement SQL interno, e chamadas entre procedures, para que eu possa rastrear o impacto de mudanças em campos de tabela ou assinaturas de procedures.

#### Acceptance Criteria

1. WHEN o Ollama_SQL_Parser processa um arquivo PL/SQL, THE Ollama_SQL_Parser SHALL extrair para cada procedure/function: nome, lista de parâmetros (nome + tipo + modo IN/OUT/IN OUT), tipo de retorno (para functions) e corpo completo.
2. WHEN o Ollama_SQL_Parser processa um arquivo PL/SQL, THE Ollama_SQL_Parser SHALL extrair para cada statement DML interno (SELECT, INSERT, UPDATE, DELETE): as colunas referenciadas por nome, a tabela alvo e o tipo de operação.
3. WHEN o Ollama_SQL_Parser extrai colunas de um statement DML, THE Ollama_SQL_Parser SHALL criar Field_Level_Nodes do tipo `column_reference` e relacionamentos `READS_COLUMN` ou `WRITES_COLUMN` entre a procedure e cada coluna.
4. WHEN o Ollama_SQL_Parser extrai um parâmetro de procedure, THE Ollama_SQL_Parser SHALL criar um Field_Level_Node com `kind = "procedure_param"`, `param_mode` (IN/OUT/IN OUT) e `data_type`, vinculado à procedure via `HAS_PARAMETER`.
5. WHEN o Ollama_SQL_Parser recebe uma resposta do qwen3-coder-next que não é JSON válido, THEN THE Ollama_SQL_Parser SHALL tentar extrair o bloco JSON da resposta usando regex, e IF a extração falhar, THEN THE Ollama_SQL_Parser SHALL registrar o arquivo como `parse_failed` e continuar o scan.
6. THE Ollama_SQL_Parser SHALL enviar ao qwen3-coder-next um prompt estruturado que solicite explicitamente: procedures, parâmetros com modo e tipo, colunas por statement DML, e chamadas entre procedures.
7. WHEN o Ollama_SQL_Parser processa um package PL/SQL, THE Ollama_SQL_Parser SHALL extrair cada procedure e function do package body como nós individuais, vinculados ao package via relacionamento `BELONGS_TO_PACKAGE`.
8. THE Ollama_SQL_Parser SHALL calcular e armazenar o Signature_Hash de cada procedure como SHA-256 de `(nome_procedure + tipos_parâmetros_ordenados + modos_parâmetros)`.

---

### Requirement 3: Deep Parsing de Angular (TypeScript/Angular)

**User Story:** Como desenvolvedor frontend, quero que o sistema extraia inputs, outputs, injeções de dependência, chamadas HTTP e bindings de template de componentes Angular, para que a análise de impacto cubra a camada de apresentação com precisão.

#### Acceptance Criteria

1. WHEN o Deep_Parser processa um arquivo `.ts` com decorator `@Component`, `@Injectable`, `@Directive` ou `@Pipe`, THE Deep_Parser SHALL identificar o artefato como Angular_Component e registrar o tipo de decorator como atributo `angular_type`.
2. WHEN o Deep_Parser processa um Angular_Component, THE Deep_Parser SHALL extrair cada propriedade decorada com `@Input()` ou `@Output()` como Field_Level_Node com `kind = "input_binding"` ou `kind = "output_binding"`, vinculado ao componente via `HAS_BINDING`.
3. WHEN o Deep_Parser processa um Angular_Component, THE Deep_Parser SHALL extrair cada parâmetro do construtor como Field_Level_Node com `kind = "injected_dependency"`, registrando o tipo injetado como `dependency_type`.
4. WHEN o Deep_Parser processa um Angular_Component, THE Deep_Parser SHALL extrair chamadas HTTP (`HttpClient.get`, `HttpClient.post`, `HttpClient.put`, `HttpClient.delete`) como relacionamentos `CALLS_HTTP` com atributos `http_method` e `url_pattern`.
5. WHEN o Deep_Parser processa um arquivo de módulo Angular (`@NgModule`), THE Deep_Parser SHALL extrair as listas `declarations`, `imports`, `exports` e `providers` e criar relacionamentos `DECLARES`, `IMPORTS_MODULE`, `EXPORTS_COMPONENT` e `PROVIDES` entre o módulo e os artefatos referenciados.
6. WHEN o Deep_Parser processa um arquivo de roteamento Angular (contendo `RouterModule.forRoot` ou `RouterModule.forChild`), THE Deep_Parser SHALL extrair cada rota como nó `Angular_Route` com atributos `path` e `component`, vinculado ao componente via `ROUTED_TO`.
7. THE Deep_Parser SHALL processar arquivos Angular usando exclusivamente o Tree_Sitter_Parser, sem depender do qwen3-coder-next para extração estrutural de TypeScript/Angular.

---

### Requirement 4: Análise de Impacto de Mudanças em Nível de Campo

**User Story:** Como desenvolvedor, quero informar uma mudança proposta (ex: renomear parâmetro, alterar tipo de coluna, modificar assinatura de método) e receber o conjunto completo de artefatos impactados com a cadeia de chamadas que justifica cada impacto, para que eu possa avaliar o risco antes de implementar a mudança.

#### Acceptance Criteria

1. WHEN o Impact_Engine recebe um Change_Descriptor do tipo `rename_parameter`, THE Impact_Engine SHALL retornar todos os artefatos que referenciam o parâmetro pelo nome original, incluindo callers diretos e indiretos até profundidade configurável (padrão: 5 níveis).
2. WHEN o Impact_Engine recebe um Change_Descriptor do tipo `change_column_type`, THE Impact_Engine SHALL retornar todas as procedures PL/SQL que leem ou escrevem a coluna afetada, todos os campos de entidade Java mapeados à coluna via `@Column(name=...)`, e todos os Angular_Components que exibem ou enviam o dado correspondente.
3. WHEN o Impact_Engine recebe um Change_Descriptor do tipo `change_method_signature`, THE Impact_Engine SHALL retornar todos os artefatos que chamam o método com a assinatura original, detectados via comparação de Signature_Hash.
4. WHEN o Impact_Engine recebe um Change_Descriptor do tipo `change_procedure_param`, THE Impact_Engine SHALL retornar todas as procedures PL/SQL que chamam a procedure alvo, todos os métodos Java que invocam a procedure via JDBC/JPA, e todos os Angular_Components que disparam a operação via HTTP.
5. FOR ALL Change_Descriptors processados pelo Impact_Engine, THE Impact_Engine SHALL incluir no Affected_Set a Call_Chain completa de cada artefato impactado, mostrando o caminho de dependência desde a origem da mudança até o artefato afetado.
6. THE Impact_Engine SHALL atribuir um Confidence_Score a cada item do Affected_Set, onde 100 indica dependência direta confirmada por AST e valores menores indicam dependências inferidas por nome ou heurística.
7. WHEN o Impact_Engine calcula o Affected_Set, THE Impact_Engine SHALL classificar cada artefato impactado em uma das categorias: `DIRECT` (dependência direta), `TRANSITIVE` (dependência transitiva), `INFERRED` (dependência inferida por nome/convenção).
8. THE Impact_Engine SHALL completar o cálculo do Affected_Set em no máximo 10 segundos para grafos com até 50.000 nós.

---

### Requirement 5: Análise de Impacto em Procedures PL/SQL

**User Story:** Como DBA, quero selecionar uma procedure PL/SQL e simular a mudança de um parâmetro (ex: status de VARCHAR2 para NUMBER), e receber a lista de todas as procedures, métodos Java e componentes Angular impactados, para que eu possa planejar a migração com segurança.

#### Acceptance Criteria

1. WHEN o usuário seleciona uma SQL_Procedure no grafo e aciona a análise de impacto de parâmetro, THE Advanced_Impact_Analyzer SHALL identificar todas as procedures PL/SQL que chamam a procedure selecionada e passam o parâmetro afetado.
2. WHEN o Advanced_Impact_Analyzer identifica callers de uma SQL_Procedure, THE Advanced_Impact_Analyzer SHALL rastrear transitivamente os callers dos callers até que não existam mais dependências ou até atingir profundidade máxima de 10 níveis.
3. WHEN o Advanced_Impact_Analyzer rastreia o impacto de uma mudança de parâmetro PL/SQL, THE Advanced_Impact_Analyzer SHALL cruzar o grafo de dependências para identificar métodos Java que invocam a procedure via `CallableStatement`, `StoredProcedure` ou anotações JPA `@NamedStoredProcedureQuery`.
4. WHEN o Advanced_Impact_Analyzer identifica métodos Java impactados por uma mudança PL/SQL, THE Advanced_Impact_Analyzer SHALL rastrear os Angular_Components que chamam os endpoints HTTP que expõem esses métodos Java.
5. THE Advanced_Impact_Analyzer SHALL apresentar o resultado como uma árvore de impacto hierárquica: `PL/SQL Procedure → Java Methods → API Endpoints → Angular Components`.
6. IF o Advanced_Impact_Analyzer não encontrar nenhum artefato impactado além da procedure selecionada, THEN THE Advanced_Impact_Analyzer SHALL retornar um resultado explícito indicando que a procedure é um artefato isolado, com Confidence_Score de 100.

---

### Requirement 6: Detecção de Quebra de Contrato

**User Story:** Como arquiteto, quero que o sistema detecte automaticamente quando uma mudança de código quebra o contrato de uma interface pública (método, endpoint, procedure), para que eu seja alertado antes de fazer o commit.

#### Acceptance Criteria

1. WHEN o Deep_Parser processa um artefato já existente no grafo, THE Deep_Parser SHALL comparar o Signature_Hash atual com o Signature_Hash armazenado e, IF os hashes diferirem, THEN THE Deep_Parser SHALL marcar o artefato com `contract_broken = true` e registrar o hash anterior em `previous_signature_hash`.
2. WHEN o Deep_Parser detecta `contract_broken = true` em um artefato, THE Advanced_Impact_Analyzer SHALL calcular automaticamente o Affected_Set para o Change_Descriptor correspondente e armazenar o resultado no nó do grafo.
3. THE Advanced_Impact_Analyzer SHALL expor via API o conjunto de artefatos com `contract_broken = true` detectados no último scan, com o Affected_Set pré-calculado para cada um.
4. WHEN o Advanced_Impact_Analyzer detecta uma quebra de contrato em um endpoint HTTP (API_Endpoint), THE Advanced_Impact_Analyzer SHALL identificar todos os Angular_Components que consomem o endpoint via `CONSUMES_API` e incluí-los no Affected_Set com categoria `DIRECT`.
5. THE Advanced_Impact_Analyzer SHALL calcular o Confidence_Score de quebras de contrato detectadas via Signature_Hash como 95 ou superior, reservando valores abaixo de 95 para dependências inferidas por heurística.

---

### Requirement 7: Rastreamento de Fluxo de Dados Coluna-a-Campo

**User Story:** Como desenvolvedor, quero rastrear o caminho completo de um dado desde uma coluna de banco de dados até o campo exibido na tela Angular, para que eu entenda o impacto de uma mudança de schema no frontend.

#### Acceptance Criteria

1. THE Advanced_Impact_Analyzer SHALL rastrear o fluxo de dados de uma coluna SQL até o campo de entidade Java mapeado via `@Column`, seguindo o relacionamento `MAPS_TO_COLUMN`.
2. WHEN o Advanced_Impact_Analyzer rastreia o fluxo de dados de um campo de entidade Java, THE Advanced_Impact_Analyzer SHALL identificar os DTOs que recebem o campo via mapeamento (MapStruct, BeanUtils, construtor explícito) e criar relacionamentos `MAPPED_FROM`.
3. WHEN o Advanced_Impact_Analyzer rastreia o fluxo de dados de um DTO Java, THE Advanced_Impact_Analyzer SHALL identificar os endpoints HTTP que retornam o DTO como corpo de resposta e criar relacionamentos `SERIALIZED_BY`.
4. WHEN o Advanced_Impact_Analyzer rastreia o fluxo de dados de um endpoint HTTP, THE Advanced_Impact_Analyzer SHALL identificar os Angular_Components que consomem o endpoint e os campos de template que exibem o dado, criando relacionamentos `DISPLAYED_BY`.
5. THE Advanced_Impact_Analyzer SHALL expor o fluxo completo `Coluna → Entidade → DTO → Endpoint → Componente Angular` como uma estrutura de dados linear ordenada, retornada pelo endpoint `/api/impact/data-flow/{column_key}`.
6. IF o Advanced_Impact_Analyzer não conseguir estabelecer um elo em algum ponto da cadeia de fluxo, THEN THE Advanced_Impact_Analyzer SHALL retornar o fluxo parcial com o elo quebrado marcado como `unresolved`, sem interromper o retorno dos elos resolvidos.

---

### Requirement 8: Análise Semântica via qwen3-coder-next

**User Story:** Como desenvolvedor, quero que o modelo qwen3-coder-next analise o impacto de uma mudança e forneça uma explicação em linguagem natural com recomendações de refatoração, para que eu entenda não apenas o que é impactado, mas por quê e como mitigar.

#### Acceptance Criteria

1. WHEN o usuário solicita análise de impacto de uma mudança, THE Advanced_Impact_Analyzer SHALL enviar ao qwen3-coder-next o Change_Descriptor, o Affected_Set calculado pelo Impact_Engine e o código-fonte dos artefatos diretamente impactados (categoria `DIRECT`).
2. THE Advanced_Impact_Analyzer SHALL instruir o qwen3-coder-next a retornar uma análise estruturada em JSON com os campos: `summary` (resumo executivo), `risk_level` (LOW/MEDIUM/HIGH/CRITICAL), `breaking_changes` (lista de quebras de contrato), `migration_steps` (passos de migração ordenados) e `estimated_effort` (estimativa em horas).
3. WHEN o qwen3-coder-next retorna uma análise, THE Advanced_Impact_Analyzer SHALL validar que o JSON contém todos os campos obrigatórios e, IF algum campo estiver ausente, THEN THE Advanced_Impact_Analyzer SHALL reenviar o prompt com instrução de correção, até 2 tentativas adicionais.
4. THE Advanced_Impact_Analyzer SHALL limitar o contexto enviado ao qwen3-coder-next a no máximo 8.000 tokens, priorizando o código dos artefatos com Confidence_Score mais alto.
5. WHEN o qwen3-coder-next não estiver disponível ou retornar erro, THE Advanced_Impact_Analyzer SHALL retornar o Affected_Set calculado pelo Impact_Engine sem a análise semântica, com flag `semantic_analysis_available = false`.
6. THE Advanced_Impact_Analyzer SHALL usar exclusivamente o modelo `qwen3-coder-next:q4_K_M` para análise semântica de impacto, sem fallback para outros modelos nesta função específica.

---

### Requirement 9: API de Análise de Impacto Avançada

**User Story:** Como desenvolvedor frontend, quero endpoints REST bem definidos para submeter Change_Descriptors e receber Affected_Sets com Call_Chains, para que eu possa integrar a análise de impacto na interface do InsightGraph.

#### Acceptance Criteria

1. THE Advanced_Impact_Analyzer SHALL expor o endpoint `POST /api/impact/analyze` que aceita um Change_Descriptor no corpo da requisição e retorna o Affected_Set com Call_Chains e Confidence_Scores.
2. THE Advanced_Impact_Analyzer SHALL expor o endpoint `GET /api/impact/data-flow/{node_key}` que retorna o fluxo de dados completo de um artefato, do banco de dados até o frontend.
3. THE Advanced_Impact_Analyzer SHALL expor o endpoint `GET /api/impact/contract-breaks` que retorna todos os artefatos com `contract_broken = true` detectados no último scan.
4. THE Advanced_Impact_Analyzer SHALL expor o endpoint `GET /api/impact/field-nodes/{node_key}` que retorna todos os Field_Level_Nodes associados a um artefato (parâmetros, campos, colunas).
5. WHEN o endpoint `POST /api/impact/analyze` recebe um Change_Descriptor inválido (campos obrigatórios ausentes ou tipo de mudança não suportado), THEN THE Advanced_Impact_Analyzer SHALL retornar HTTP 422 com uma mensagem de erro descritiva indicando qual campo está inválido.
6. THE Advanced_Impact_Analyzer SHALL retornar todos os endpoints de análise de impacto com tempo de resposta inferior a 15 segundos para grafos com até 50.000 nós.

---

### Requirement 10: Persistência e Indexação de Field_Level_Nodes no Neo4j

**User Story:** Como arquiteto, quero que os Field_Level_Nodes (parâmetros, campos, colunas) sejam persistidos no Neo4j com índices adequados, para que as consultas de impacto sejam executadas com precisão e performance.

#### Acceptance Criteria

1. THE Advanced_Impact_Analyzer SHALL criar índices Neo4j para Field_Level_Nodes nas propriedades `namespace_key`, `kind`, `data_type` e `parent_key` durante a inicialização do sistema.
2. WHEN o Deep_Parser ou Ollama_SQL_Parser cria um Field_Level_Node, THE Advanced_Impact_Analyzer SHALL persistir o nó no Neo4j com label `Field_Level_Node` e label adicional correspondente ao `kind` (`Parameter`, `Column`, `Input_Binding`, `Output_Binding`, `Injected_Dependency`).
3. THE Advanced_Impact_Analyzer SHALL usar operações `MERGE` do Cypher para todos os Field_Level_Nodes, garantindo que rescans não criem nós duplicados.
4. WHEN o Neo4j não estiver disponível, THE Advanced_Impact_Analyzer SHALL armazenar Field_Level_Nodes na estrutura em memória existente (`memory_nodes`) e manter os relacionamentos em `memory_edges`, garantindo que a análise de impacto funcione sem Neo4j.
5. THE Advanced_Impact_Analyzer SHALL armazenar o Signature_Hash de cada artefato como propriedade `signature_hash` no nó Neo4j correspondente, permitindo detecção de quebra de contrato em rescans incrementais.

---

### Requirement 11: Precisão e Validação da Análise

**User Story:** Como arquiteto, quero que o sistema indique explicitamente o nível de confiança de cada impacto detectado e distinga entre dependências confirmadas por AST e dependências inferidas, para que eu não tome decisões baseadas em falsos positivos.

#### Acceptance Criteria

1. THE Impact_Engine SHALL atribuir Confidence_Score 100 apenas a dependências confirmadas por relacionamento direto no grafo AST (ex: chamada de método resolvida por namespace_key exato).
2. THE Impact_Engine SHALL atribuir Confidence_Score entre 70 e 99 a dependências resolvidas por correspondência de nome qualificado (ex: nome de classe + nome de método sem namespace_key exato).
3. THE Impact_Engine SHALL atribuir Confidence_Score entre 40 e 69 a dependências inferidas por convenção de nomenclatura ou heurística (ex: campo `userId` provavelmente mapeia para coluna `user_id`).
4. THE Impact_Engine SHALL atribuir Confidence_Score abaixo de 40 a dependências inferidas por análise semântica do qwen3-coder-next sem confirmação estrutural.
5. THE Advanced_Impact_Analyzer SHALL incluir no resultado da análise de impacto um campo `analysis_metadata` com: `total_affected`, `high_confidence_count` (score >= 70), `low_confidence_count` (score < 70), `parse_errors` e `unresolved_links`.
6. WHEN o Affected_Set contiver artefatos com Confidence_Score abaixo de 40, THE Advanced_Impact_Analyzer SHALL sinalizar esses artefatos com flag `requires_manual_review = true`.
