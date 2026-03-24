# Requirements Document

## Introduction

Este documento define os requisitos para o sistema de análise autônoma CodeQL, que permite aos usuários executar análises de segurança completas através de uma interface frontend, sem necessidade de comandos CLI manuais. O sistema deve funcionar de forma similar ao CAST, oferecendo análise end-to-end automatizada incluindo criação/atualização de banco de dados, execução de análise e ingestão de resultados no Neo4j, com suporte para múltiplos projetos.

## Glossary

- **CodeQL_System**: Sistema completo de análise autônoma CodeQL
- **Frontend_UI**: Interface React/TypeScript do usuário
- **Backend_API**: API FastAPI que gerencia operações CodeQL
- **CodeQL_CLI**: Ferramenta de linha de comando CodeQL instalada em C:\codeql\codeql\
- **Database_Manager**: Componente responsável por criar e atualizar bancos de dados CodeQL
- **Analysis_Engine**: Componente que executa queries CodeQL e gera SARIF
- **SARIF_Ingestor**: Componente que processa resultados SARIF e insere no Neo4j
- **Project_Registry**: Registro de projetos configurados para análise
- **Analysis_Job**: Tarefa de análise em execução ou concluída
- **SARIF_Result**: Arquivo de saída contendo vulnerabilidades detectadas

## Requirements

### Requirement 1: Frontend Trigger Interface

**User Story:** Como usuário, eu quero clicar em um botão no frontend para iniciar análise CodeQL, para que eu não precise executar comandos CLI manualmente.

#### Acceptance Criteria

1. THE Frontend_UI SHALL exibir um botão "Executar Análise CodeQL" acessível na interface principal
2. WHEN o usuário clica no botão de análise, THE Frontend_UI SHALL exibir um modal de configuração de análise
3. THE Frontend_UI SHALL permitir seleção de projeto(s) a serem analisados através de dropdown ou lista
4. THE Frontend_UI SHALL exibir progresso em tempo real da análise (criação de DB, análise, ingestão)
5. WHEN a análise é iniciada, THE Frontend_UI SHALL desabilitar o botão e exibir status "Em Execução"
6. WHEN a análise é concluída, THE Frontend_UI SHALL exibir resumo com total de vulnerabilidades encontradas
7. IF ocorrer erro durante análise, THEN THE Frontend_UI SHALL exibir mensagem de erro descritiva

### Requirement 2: Autonomous Database Management

**User Story:** Como desenvolvedor, eu quero que o sistema crie e atualize bancos de dados CodeQL automaticamente, para que eu não precise gerenciar databases manualmente.

#### Acceptance Criteria

1. THE Database_Manager SHALL verificar se banco de dados CodeQL existe para o projeto selecionado
2. IF banco de dados não existe, THEN THE Database_Manager SHALL criar novo banco de dados automaticamente
3. IF banco de dados existe, THEN THE Database_Manager SHALL atualizar o banco com código fonte mais recente
4. THE Database_Manager SHALL detectar linguagem do projeto automaticamente (Java, JavaScript, TypeScript)
5. THE Database_Manager SHALL armazenar databases em diretório configurável (padrão: C:\codeql\databases\)
6. WHEN criação de database falha, THE Database_Manager SHALL retornar erro com detalhes do problema
7. THE Database_Manager SHALL reportar progresso de criação/atualização (0-100%)

### Requirement 3: Automated Analysis Execution

**User Story:** Como usuário, eu quero que o sistema execute análise CodeQL automaticamente após preparar o database, para que o processo seja completamente autônomo.

#### Acceptance Criteria

1. WHEN database está pronto, THE Analysis_Engine SHALL executar análise CodeQL automaticamente
2. THE Analysis_Engine SHALL usar suite "security-extended" como padrão
3. THE Analysis_Engine SHALL gerar arquivo SARIF com resultados da análise
4. THE Analysis_Engine SHALL armazenar SARIF em diretório temporário com nome único
5. THE Analysis_Engine SHALL reportar progresso de análise (0-100%)
6. WHEN análise é concluída, THE Analysis_Engine SHALL retornar caminho do arquivo SARIF
7. IF análise exceder timeout de 600 segundos, THEN THE Analysis_Engine SHALL cancelar e reportar timeout

### Requirement 4: SARIF Ingestion Pipeline

**User Story:** Como usuário, eu quero que vulnerabilidades detectadas sejam automaticamente inseridas no Neo4j, para que eu possa visualizá-las no grafo.

#### Acceptance Criteria

1. WHEN arquivo SARIF é gerado, THE SARIF_Ingestor SHALL processar resultados automaticamente
2. THE SARIF_Ingestor SHALL criar nós SecurityIssue no Neo4j para cada vulnerabilidade
3. THE SARIF_Ingestor SHALL criar relacionamentos HAS_VULNERABILITY entre entidades e vulnerabilidades
4. THE SARIF_Ingestor SHALL marcar caminhos contaminados com propriedade is_tainted
5. THE SARIF_Ingestor SHALL mapear localizações SARIF para entidades existentes no grafo
6. WHEN ingestão é concluída, THE SARIF_Ingestor SHALL retornar resumo com contadores (total, ingeridos, ignorados)
7. IF entidade não é encontrada para vulnerabilidade, THEN THE SARIF_Ingestor SHALL criar SecurityIssue órfão

### Requirement 5: Multi-Project Support

**User Story:** Como usuário, eu quero analisar múltiplos projetos simultaneamente, para que eu possa avaliar segurança de todo o ecossistema.

#### Acceptance Criteria

1. THE Project_Registry SHALL armazenar configuração de múltiplos projetos
2. THE Frontend_UI SHALL permitir seleção de múltiplos projetos para análise simultânea
3. WHEN múltiplos projetos são selecionados, THE Backend_API SHALL executar análises em paralelo
4. THE Backend_API SHALL limitar execuções paralelas a 3 projetos simultâneos
5. THE Frontend_UI SHALL exibir progresso individual de cada projeto
6. WHEN todas análises são concluídas, THE Backend_API SHALL retornar resumo consolidado
7. THE Project_Registry SHALL persistir configurações em arquivo JSON

### Requirement 6: Project Configuration Management

**User Story:** Como administrador, eu quero configurar projetos para análise CodeQL, para que o sistema saiba onde encontrar código fonte e onde armazenar databases.

#### Acceptance Criteria

1. THE Backend_API SHALL fornecer endpoint POST /api/codeql/projects para adicionar projetos
2. THE Backend_API SHALL fornecer endpoint GET /api/codeql/projects para listar projetos configurados
3. THE Backend_API SHALL fornecer endpoint DELETE /api/codeql/projects/{id} para remover projetos
4. THE Project_Registry SHALL armazenar nome, caminho fonte, linguagem e caminho database para cada projeto
5. THE Frontend_UI SHALL exibir interface de gerenciamento de projetos
6. WHEN projeto é adicionado, THE Backend_API SHALL validar que caminho fonte existe
7. THE Project_Registry SHALL gerar ID único para cada projeto

### Requirement 7: Real-Time Progress Tracking

**User Story:** Como usuário, eu quero ver progresso em tempo real da análise, para que eu saiba quanto tempo falta e qual etapa está executando.

#### Acceptance Criteria

1. THE Backend_API SHALL manter estado de cada Analysis_Job em memória
2. THE Backend_API SHALL fornecer endpoint GET /api/codeql/status/{job_id} para consultar progresso
3. THE Frontend_UI SHALL fazer polling de status a cada 2 segundos durante análise
4. THE Backend_API SHALL reportar etapa atual (database_creation, analysis, ingestion)
5. THE Backend_API SHALL reportar percentual de progresso (0-100) para cada etapa
6. THE Backend_API SHALL reportar arquivo atual sendo processado durante criação de database
7. WHEN análise é concluída, THE Backend_API SHALL manter histórico por 1 hora

### Requirement 8: Error Handling and Recovery

**User Story:** Como usuário, eu quero que o sistema trate erros graciosamente e forneça informações úteis, para que eu possa corrigir problemas.

#### Acceptance Criteria

1. IF CodeQL_CLI não está instalado, THEN THE Backend_API SHALL retornar erro "CodeQL CLI não encontrado"
2. IF caminho de projeto não existe, THEN THE Backend_API SHALL retornar erro "Projeto não encontrado"
3. IF Neo4j está desconectado, THEN THE Backend_API SHALL retornar erro "Neo4j indisponível"
4. IF análise falha, THEN THE Backend_API SHALL incluir stderr do CodeQL_CLI na resposta
5. THE Backend_API SHALL registrar todos erros em log com nível ERROR
6. WHEN erro ocorre, THE Analysis_Job SHALL marcar status como "failed" com mensagem de erro
7. THE Frontend_UI SHALL exibir erros em modal com opção de copiar detalhes

### Requirement 9: Analysis History and Results

**User Story:** Como usuário, eu quero visualizar histórico de análises executadas, para que eu possa comparar resultados ao longo do tempo.

#### Acceptance Criteria

1. THE Backend_API SHALL armazenar histórico de análises em arquivo JSON
2. THE Backend_API SHALL fornecer endpoint GET /api/codeql/history para listar análises
3. THE Backend_API SHALL armazenar timestamp, projeto, duração e resumo para cada análise
4. THE Frontend_UI SHALL exibir tabela de histórico com filtros por projeto e data
5. THE Frontend_UI SHALL permitir visualizar detalhes de análise anterior
6. THE Backend_API SHALL manter histórico dos últimos 100 análises
7. WHEN histórico excede 100 entradas, THE Backend_API SHALL remover análises mais antigas

### Requirement 10: Integration with Existing Features

**User Story:** Como usuário, eu quero que vulnerabilidades CodeQL sejam integradas com funcionalidades existentes, para que eu tenha visão unificada de segurança.

#### Acceptance Criteria

1. THE Frontend_UI SHALL exibir badge de vulnerabilidades em nós do grafo
2. THE ImpactAnalysisPanel SHALL incluir aba "Segurança" mostrando vulnerabilidades do nó
3. THE GraphCanvas SHALL colorir arestas contaminadas (is_tainted) em vermelho
4. THE Backend_API SHALL incluir contagem de vulnerabilidades em endpoint /api/stats
5. THE FragilityCalculator SHALL incorporar vulnerabilidades no cálculo de fragilidade
6. WHEN nó com vulnerabilidades é selecionado, THE Frontend_UI SHALL destacar caminhos contaminados
7. THE Backend_API SHALL fornecer endpoint GET /api/codeql/vulnerabilities/{node_key} para consultar vulnerabilidades de nó específico

### Requirement 11: CodeQL CLI Path Configuration

**User Story:** Como administrador, eu quero configurar caminho do CodeQL CLI, para que o sistema funcione em diferentes ambientes.

#### Acceptance Criteria

1. THE Backend_API SHALL ler caminho do CodeQL_CLI de variável de ambiente CODEQL_PATH
2. IF CODEQL_PATH não está definida, THEN THE Backend_API SHALL usar caminho padrão C:\codeql\codeql\codeql.exe
3. THE Backend_API SHALL validar que CodeQL_CLI existe no caminho configurado durante inicialização
4. THE Backend_API SHALL incluir versão do CodeQL_CLI em endpoint /api/health
5. THE Backend_API SHALL registrar caminho do CodeQL_CLI em log durante startup
6. IF CodeQL_CLI não é encontrado, THEN THE Backend_API SHALL registrar warning mas continuar inicialização
7. THE Backend_API SHALL fornecer endpoint GET /api/codeql/config para consultar configuração

### Requirement 12: Background Job Management

**User Story:** Como desenvolvedor, eu quero que análises executem em background, para que não bloqueiem outras operações da API.

#### Acceptance Criteria

1. THE Backend_API SHALL executar análises usando BackgroundTasks do FastAPI
2. THE Backend_API SHALL retornar job_id imediatamente após iniciar análise
3. THE Backend_API SHALL permitir múltiplas análises simultâneas (máximo 3)
4. WHEN limite de análises simultâneas é atingido, THE Backend_API SHALL enfileirar novas requisições
5. THE Backend_API SHALL processar fila de análises em ordem FIFO
6. THE Backend_API SHALL fornecer endpoint DELETE /api/codeql/jobs/{job_id} para cancelar análise
7. WHEN análise é cancelada, THE Backend_API SHALL terminar processo CodeQL_CLI

### Requirement 13: SARIF Result Persistence

**User Story:** Como usuário, eu quero que arquivos SARIF sejam preservados, para que eu possa analisá-los posteriormente com outras ferramentas.

#### Acceptance Criteria

1. THE Backend_API SHALL armazenar arquivos SARIF em diretório configurável (padrão: ./codeql-results/)
2. THE Backend_API SHALL nomear arquivos SARIF com padrão {project_name}_{timestamp}.sarif
3. THE Backend_API SHALL fornecer endpoint GET /api/codeql/sarif/{job_id} para download de SARIF
4. THE Backend_API SHALL manter arquivos SARIF por 30 dias
5. THE Backend_API SHALL fornecer endpoint DELETE /api/codeql/sarif/{job_id} para remover SARIF
6. WHEN espaço em disco é insuficiente, THE Backend_API SHALL remover SARIFs mais antigos automaticamente
7. THE Backend_API SHALL incluir tamanho de arquivo SARIF em resposta de histórico

### Requirement 14: Query Suite Selection

**User Story:** Como usuário avançado, eu quero selecionar suite de queries CodeQL, para que eu possa customizar profundidade da análise.

#### Acceptance Criteria

1. THE Frontend_UI SHALL fornecer dropdown para seleção de suite (security-extended, security-and-quality, security-critical)
2. THE Backend_API SHALL aceitar parâmetro suite em endpoint de análise
3. THE Backend_API SHALL usar "security-extended" como suite padrão
4. THE Backend_API SHALL validar que suite selecionada é válida
5. THE Backend_API SHALL passar suite para CodeQL_CLI via parâmetro --suite
6. THE Backend_API SHALL armazenar suite utilizada no histórico de análise
7. THE Frontend_UI SHALL exibir descrição de cada suite ao passar mouse sobre opção

### Requirement 15: Database Update Strategy

**User Story:** Como usuário, eu quero escolher entre criar novo database ou atualizar existente, para que eu possa otimizar tempo de análise.

#### Acceptance Criteria

1. THE Frontend_UI SHALL fornecer opção "Forçar Recriação de Database"
2. IF opção está desmarcada E database existe, THEN THE Database_Manager SHALL atualizar database existente
3. IF opção está marcada OU database não existe, THEN THE Database_Manager SHALL criar novo database
4. THE Database_Manager SHALL usar comando "codeql database upgrade" para atualizar databases
5. THE Database_Manager SHALL verificar idade do database antes de decidir atualizar
6. IF database tem mais de 7 dias, THEN THE Database_Manager SHALL recomendar recriação
7. THE Frontend_UI SHALL exibir idade do database na interface de configuração
