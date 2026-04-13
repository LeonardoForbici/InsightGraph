# Requirements Document

## Introduction

Este documento especifica os requisitos para aprimoramento do sistema de scanner do InsightGraph e adição de funcionalidade beta de controle por gestos. O sistema permitirá análise de código local e remoto (GitHub), além de manipulação visual de nós do grafo usando webcam e reconhecimento de gestos das mãos.

## Glossary

- **Scanner**: Componente responsável por análise estática de código-fonte e construção do grafo de dependências
- **Local_Scanner**: Modo de scanner que analisa código em diretórios locais do sistema de arquivos
- **GitHub_Scanner**: Modo de scanner que clona e analisa repositórios remotos do GitHub
- **Hand_Gesture_Controller**: Sistema de reconhecimento de gestos das mãos usando webcam para manipulação do grafo
- **Graph_Node**: Nó individual no grafo de dependências (classe, método, componente, etc.)
- **MediaPipe**: Biblioteca do Google para tracking de mãos em tempo real
- **Neon_Effect**: Efeito visual com cores brilhantes (cyan, magenta, azul) sobre fundo preto
- **Gesture_Recognition**: Processo de identificação de padrões de movimento das mãos para comandos
- **Fork_Node**: Nó do grafo que representa um ponto de bifurcação ou dependência múltipla

## Requirements

### Requirement 1: Scanner Local Aprimorado

**User Story:** Como desenvolvedor, eu quero escanear código-fonte em diretórios locais, para que eu possa analisar projetos sem necessidade de repositório remoto

#### Acceptance Criteria

1. WHEN um caminho de diretório local é fornecido, THE Local_Scanner SHALL validar a existência do diretório
2. WHEN o diretório é válido, THE Local_Scanner SHALL identificar recursivamente todos os arquivos de código suportados (.java, .ts, .tsx, .sql)
3. WHEN arquivos são identificados, THE Local_Scanner SHALL processar cada arquivo usando os parsers Tree-Sitter apropriados
4. THE Local_Scanner SHALL extrair classes, métodos, funções, componentes e suas dependências de cada arquivo
5. WHEN a extração é completa, THE Local_Scanner SHALL persistir os nós e arestas no Neo4j e na memória
6. THE Local_Scanner SHALL calcular métricas de complexidade, acoplamento e hotspot para cada nó
7. WHEN o scan é concluído, THE Local_Scanner SHALL atualizar o índice RAG com embeddings dos novos nós
8. THE Local_Scanner SHALL reportar progresso em tempo real (arquivos processados, nós criados, porcentagem)
9. IF um erro ocorre durante o scan, THEN THE Local_Scanner SHALL registrar o erro e continuar com os próximos arquivos
10. WHEN o scan termina, THE Local_Scanner SHALL emitir evento SSE "graph_updated" para notificar o frontend

### Requirement 2: Scanner com Configuração GitHub

**User Story:** Como desenvolvedor, eu quero escanear repositórios remotos do GitHub, para que eu possa analisar projetos sem cloná-los manualmente

#### Acceptance Criteria

1. THE GitHub_Scanner SHALL aceitar configuração com repositório (owner/repo), branch, token de autenticação e opção de clone shallow
2. WHEN configuração é fornecida, THE GitHub_Scanner SHALL validar o formato do repositório (owner/repo)
3. WHEN a configuração é válida, THE GitHub_Scanner SHALL clonar o repositório em diretório temporário usando git
4. WHERE shallow clone está habilitado, THE GitHub_Scanner SHALL clonar apenas o último commit (--depth=1)
5. WHERE token de autenticação é fornecido, THE GitHub_Scanner SHALL usar o token para autenticação HTTPS
6. WHEN o clone é completo, THE GitHub_Scanner SHALL invocar o Local_Scanner no diretório clonado
7. WHEN o scan termina, THE GitHub_Scanner SHALL limpar o diretório temporário de forma segura
8. IF o clone falha por autenticação, THEN THE GitHub_Scanner SHALL retornar erro descritivo sobre credenciais
9. IF o clone falha por repositório inexistente, THEN THE GitHub_Scanner SHALL retornar erro descritivo sobre o repositório
10. THE GitHub_Scanner SHALL persistir a configuração do GitHub no localStorage do frontend para reutilização

### Requirement 3: API de Configuração do Scanner

**User Story:** Como desenvolvedor, eu quero configurar o modo de scanner (local ou GitHub), para que eu possa escolher a fonte de código a analisar

#### Acceptance Criteria

1. THE Scanner_API SHALL expor endpoint POST /api/scan com parâmetros mode, paths, github_config
2. WHEN mode é "local", THE Scanner_API SHALL validar que paths contém pelo menos um diretório
3. WHEN mode é "github", THE Scanner_API SHALL validar que github_config contém repository e branch
4. THE Scanner_API SHALL iniciar o scan em background task assíncrona
5. THE Scanner_API SHALL retornar imediatamente com status 202 Accepted
6. THE Scanner_API SHALL expor endpoint GET /api/scan/status para polling de progresso
7. THE Scanner_API SHALL expor endpoint POST /api/scan/cancel para cancelamento de scan em andamento
8. WHEN scan é cancelado, THE Scanner_API SHALL interromper o processamento e limpar recursos temporários
9. THE Scanner_API SHALL persistir configurações de scan no state_store para recuperação após restart
10. THE Scanner_API SHALL validar que apenas um scan pode executar por vez

### Requirement 4: Hand Gesture Controller - Tracking de Mãos

**User Story:** Como usuário, eu quero ativar tracking de mãos via webcam, para que eu possa manipular o grafo usando gestos

#### Acceptance Criteria

1. THE Hand_Gesture_Controller SHALL inicializar MediaPipe Hands com confiança mínima de 0.7
2. WHEN webcam é ativada, THE Hand_Gesture_Controller SHALL capturar frames em tempo real usando OpenCV
3. THE Hand_Gesture_Controller SHALL detectar até 2 mãos simultaneamente no frame
4. WHEN uma mão é detectada, THE Hand_Gesture_Controller SHALL extrair 21 landmarks (pontos) da mão
5. THE Hand_Gesture_Controller SHALL calcular coordenadas normalizadas (0-1) para cada landmark
6. THE Hand_Gesture_Controller SHALL calcular velocidade de movimento de cada ponta de dedo entre frames
7. THE Hand_Gesture_Controller SHALL executar em thread separada para não bloquear o processamento principal
8. THE Hand_Gesture_Controller SHALL expor endpoint WebSocket /ws/hand-tracking para streaming de dados
9. WHEN conexão WebSocket é estabelecida, THE Hand_Gesture_Controller SHALL enviar landmarks a cada frame processado
10. IF webcam não está disponível, THEN THE Hand_Gesture_Controller SHALL retornar erro descritivo

### Requirement 5: Hand Gesture Controller - Efeitos Visuais Neon

**User Story:** Como usuário, eu quero ver efeitos visuais neon nas minhas mãos, para que eu tenha feedback visual do tracking

#### Acceptance Criteria

1. THE Neon_Renderer SHALL renderizar fundo preto (RGB 0, 0, 0) no canvas de visualização
2. WHEN landmarks são recebidos, THE Neon_Renderer SHALL desenhar círculos nas pontas dos dedos com cores neon
3. THE Neon_Renderer SHALL usar paleta de cores neon: cyan (#00FFFF), magenta (#FF00FF), azul (#0080FF)
4. THE Neon_Renderer SHALL desenhar linhas brilhantes das pontas dos dedos até o centro da palma
5. THE Neon_Renderer SHALL adicionar partículas brilhantes ao longo das linhas com efeito de trail
6. WHEN velocidade de dedo excede threshold, THE Neon_Renderer SHALL aumentar brilho das linhas proporcionalmente
7. THE Neon_Renderer SHALL ciclar lentamente entre cores neon (transição de 3 segundos por cor)
8. THE Neon_Renderer SHALL desenhar threads finos entre pontas de dedos adjacentes (polegar-indicador, indicador-médio, etc)
9. THE Neon_Renderer SHALL aplicar efeito de glow (blur) nas linhas e partículas para aparência neon
10. THE Neon_Renderer SHALL manter taxa de 30 FPS mínimo para fluidez visual

### Requirement 6: Hand Gesture Controller - Reconhecimento de Gestos

**User Story:** Como usuário, eu quero usar gestos específicos para comandos, para que eu possa manipular nós do grafo sem mouse

#### Acceptance Criteria

1. THE Gesture_Recognizer SHALL detectar gesto "pinça" (polegar e indicador próximos) para selecionar nó
2. WHEN gesto "pinça" é detectado sobre um Graph_Node, THE Gesture_Recognizer SHALL selecionar o nó
3. THE Gesture_Recognizer SHALL detectar gesto "mão aberta" (todos dedos estendidos) para arrastar nó
4. WHEN gesto "arrastar" é ativo, THE Gesture_Recognizer SHALL mover o nó selecionado seguindo a posição da mão
5. THE Gesture_Recognizer SHALL detectar gesto "punho fechado" para deselecionar nó
6. THE Gesture_Recognizer SHALL detectar gesto "dois dedos em V" para zoom in
7. THE Gesture_Recognizer SHALL detectar gesto "dois dedos fechando" para zoom out
8. THE Gesture_Recognizer SHALL detectar gesto "palma para frente" para pausar tracking
9. THE Gesture_Recognizer SHALL mapear coordenadas da mão (0-1) para coordenadas do canvas do grafo
10. THE Gesture_Recognizer SHALL aplicar suavização (smoothing) nos movimentos para evitar jitter

### Requirement 7: Hand Gesture Controller - Integração com Grafo

**User Story:** Como usuário, eu quero que gestos manipulem os nós do grafo, para que eu possa reorganizar visualmente as dependências

#### Acceptance Criteria

1. WHEN Hand_Gesture_Controller está ativo, THE Graph_Canvas SHALL aceitar comandos de gesto além de mouse
2. WHEN um nó é selecionado por gesto, THE Graph_Canvas SHALL destacar o nó com borda neon
3. WHEN um nó é arrastado por gesto, THE Graph_Canvas SHALL atualizar posição do nó em tempo real
4. THE Graph_Canvas SHALL persistir novas posições de nós após manipulação por gesto
5. WHEN zoom por gesto é aplicado, THE Graph_Canvas SHALL animar transição de zoom suavemente
6. THE Graph_Canvas SHALL exibir cursor virtual (círculo neon) na posição da mão detectada
7. WHEN múltiplas mãos são detectadas, THE Graph_Canvas SHALL usar mão direita como primária
8. THE Graph_Canvas SHALL ignorar gestos quando mão está fora da área do canvas
9. WHEN gesto é reconhecido, THE Graph_Canvas SHALL emitir feedback visual (flash neon) no cursor
10. THE Graph_Canvas SHALL manter compatibilidade total com controles de mouse existentes

### Requirement 8: Hand Gesture Controller - Controle de Ativação

**User Story:** Como usuário, eu quero ativar/desativar o controle por gestos, para que eu possa escolher quando usar essa funcionalidade

#### Acceptance Criteria

1. THE Frontend SHALL exibir botão toggle "Controle por Gestos (Beta)" na interface
2. WHEN botão é clicado, THE Frontend SHALL solicitar permissão de acesso à webcam
3. IF permissão é concedida, THEN THE Frontend SHALL iniciar Hand_Gesture_Controller
4. WHEN Hand_Gesture_Controller está ativo, THE Frontend SHALL exibir preview da webcam em miniatura
5. THE Frontend SHALL exibir indicador visual (ícone neon pulsante) quando gestos estão ativos
6. WHEN botão é clicado novamente, THE Frontend SHALL desativar Hand_Gesture_Controller e liberar webcam
7. THE Frontend SHALL persistir preferência de ativação no localStorage
8. THE Frontend SHALL exibir badge "BETA" próximo ao botão de controle por gestos
9. WHERE Hand_Gesture_Controller está ativo, THE Frontend SHALL exibir tooltip com gestos disponíveis
10. THE Frontend SHALL desativar automaticamente Hand_Gesture_Controller se webcam é desconectada

### Requirement 9: Hand Gesture Controller - Performance e Recursos

**User Story:** Como usuário, eu quero que o controle por gestos não afete a performance do sistema, para que eu possa usar a funcionalidade sem travamentos

#### Acceptance Criteria

1. THE Hand_Gesture_Controller SHALL processar frames em resolução máxima de 640x480 para otimização
2. THE Hand_Gesture_Controller SHALL limitar processamento a 30 FPS máximo
3. THE Hand_Gesture_Controller SHALL executar inferência MediaPipe em thread separada do rendering
4. THE Hand_Gesture_Controller SHALL liberar recursos de webcam imediatamente quando desativado
5. WHEN CPU usage excede 80%, THE Hand_Gesture_Controller SHALL reduzir FPS automaticamente
6. THE Hand_Gesture_Controller SHALL usar modelo MediaPipe Lite para dispositivos com GPU limitada
7. THE Hand_Gesture_Controller SHALL implementar debouncing de 100ms para reconhecimento de gestos
8. THE Hand_Gesture_Controller SHALL limpar buffers de frames a cada 60 frames processados
9. THE Hand_Gesture_Controller SHALL monitorar latência de processamento e alertar se exceder 100ms
10. THE Hand_Gesture_Controller SHALL gracefully degradar para modo "tracking only" se performance cair abaixo de 15 FPS

### Requirement 10: Hand Gesture Controller - Tratamento de Erros

**User Story:** Como usuário, eu quero mensagens claras quando o controle por gestos falha, para que eu possa resolver problemas

#### Acceptance Criteria

1. IF webcam não é detectada, THEN THE Frontend SHALL exibir mensagem "Webcam não encontrada"
2. IF permissão de webcam é negada, THEN THE Frontend SHALL exibir mensagem "Permissão de webcam necessária" com instruções
3. IF MediaPipe falha ao carregar, THEN THE Frontend SHALL exibir mensagem "Erro ao carregar modelo de tracking"
4. IF conexão WebSocket falha, THEN THE Frontend SHALL tentar reconectar automaticamente até 3 vezes
5. IF reconexão falha, THEN THE Frontend SHALL desativar Hand_Gesture_Controller e notificar usuário
6. WHEN erro ocorre durante tracking, THE Hand_Gesture_Controller SHALL registrar erro no console e continuar processamento
7. IF frame rate cai abaixo de 10 FPS, THEN THE Frontend SHALL exibir warning "Performance baixa detectada"
8. THE Frontend SHALL exibir mensagem de compatibilidade se navegador não suporta getUserMedia
9. THE Frontend SHALL validar que backend Python está disponível antes de ativar Hand_Gesture_Controller
10. THE Frontend SHALL exibir mensagem específica se dependências Python (MediaPipe, OpenCV) não estão instaladas

### Requirement 11: Integração Scanner Aprimorado com Sistema Existente

**User Story:** Como desenvolvedor, eu quero que o scanner aprimorado integre com funcionalidades existentes, para que não haja quebra de compatibilidade

#### Acceptance Criteria

1. THE Enhanced_Scanner SHALL manter compatibilidade com endpoints existentes /api/scan e /api/scan/status
2. THE Enhanced_Scanner SHALL continuar atualizando scan_state global para compatibilidade com polling
3. THE Enhanced_Scanner SHALL emitir eventos SSE "graph_updated" após scan completo
4. THE Enhanced_Scanner SHALL integrar com IncrementalScanner para watch mode existente
5. THE Enhanced_Scanner SHALL persistir resultados no mesmo formato Neo4j existente
6. THE Enhanced_Scanner SHALL atualizar memory_nodes e memory_edges para compatibilidade com grafo em memória
7. THE Enhanced_Scanner SHALL invocar ImpactEngine após scan para cálculo de métricas
8. THE Enhanced_Scanner SHALL atualizar RagStore com embeddings para busca semântica
9. THE Enhanced_Scanner SHALL registrar histórico de scan no state_store
10. THE Enhanced_Scanner SHALL manter suporte a multi-tenant se TENANT_ID está configurado

### Requirement 12: Documentação e Apresentação ao Cliente

**User Story:** Como apresentador, eu quero demonstrar o controle por gestos ao cliente, para que eu possa mostrar inovação do produto

#### Acceptance Criteria

1. THE Documentation SHALL incluir guia de instalação de dependências (MediaPipe, OpenCV)
2. THE Documentation SHALL incluir tutorial com screenshots de cada gesto suportado
3. THE Documentation SHALL incluir vídeo de demonstração do controle por gestos (máximo 2 minutos)
4. THE Documentation SHALL incluir seção de troubleshooting para problemas comuns de webcam
5. THE Documentation SHALL incluir requisitos mínimos de hardware (webcam 720p, CPU quad-core)
6. THE Frontend SHALL incluir modo "Demo" que exibe overlay com nomes dos gestos detectados
7. THE Frontend SHALL incluir tour guiado (onboarding) na primeira ativação do controle por gestos
8. THE Frontend SHALL permitir gravação de sessão de gestos para compartilhamento
9. THE Documentation SHALL incluir comparação de performance entre modos Local e GitHub scanner
10. THE Documentation SHALL incluir roadmap de funcionalidades futuras para controle por gestos

