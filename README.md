# InsightGraph 🚀

**Transforme código em conhecimento estruturado.**

O InsightGraph é uma engine local-first que converte bases de código em um grafo de conhecimento navegável, utilizando LLMs multi-tier + RAG (Retrieval-Augmented Generation).

---

## 🔥 Visão Geral

O InsightGraph vai além de um simples analisador de código:

* 🧠 **Entende arquitetura, relações e responsabilidades**
* ⚡ **Executa 100% localmente (privacidade total)**
* 🔍 **Permite consultas inteligentes sobre o código**
* 🕸️ **Gera um grafo navegável no Neo4j**
* 📦 **Usa pipeline multi-modelo otimizado por custo/performance**

---

## 🧠 Arquitetura de IA (Multi-Tier)

O InsightGraph utiliza uma arquitetura em camadas para equilibrar velocidade, custo computacional e profundidade de análise:

| Tier | Nome | Modelo | Função |
| :--- | :--- | :--- | :--- |
| ⚡ Tier 1 | Scout Layer | `qwen2.5-coder:1.5b` | Scan rápido e extração inicial |
| 💬 Tier 2 | Reasoning Layer | `qwen3.5:4b` | Interpretação e contexto semântico |
| 🧠 Tier 3 | Deep Analysis Layer | `qwen3-coder-next:q4_K_M` | Relações complexas e arquitetura |
| 🔎 Embeddings | RAG Layer | `nomic-embed-text` | Indexação semântica e busca |

💡 *O sistema escolhe automaticamente o nível de inteligência necessário para cada tarefa.*

---

## 🏗️ Pipeline de Funcionamento

1.  **Codebase**
2.  ↓
3.  **⚡ Fast Scan (Scout Layer)**
4.  ↓
5.  **📦 Extração de entidades (classes, funções, módulos)**
6.  ↓
7.  **🔎 Indexação semântica (RAG)**
8.  ↓
9.  **🧠 Análise profunda (Deep Layer)**
10. ↓
11. **🕸️ Persistência no Neo4j**
12. ↓
13. **📊 Visualização + Query inteligente**

---

## 🧩 Principais Features

### 🔍 Análise de Código
* Parsing inteligente de múltiplas linguagens
* Identificação de padrões arquiteturais
* Extração de dependências e responsabilidades

### 🧠 RAG (Memória Semântica)
* Armazena contexto do projeto
* Permite Q&A sobre o código
* Evita reprocessamento desnecessário

### 🕸️ Grafo de Conhecimento
* **Nós:** arquivos, classes, funções
* **Relações:** dependências, chamadas, hierarquias
* **Persistência em Neo4j**

### ⚡ Análise Incremental
* Usa `state.db` para evitar retrabalho
* Reprocessa apenas mudanças

### 📊 Relatórios Automatizados
* Geração via templates (Jinja2)
* Sumários arquiteturais
* Insights estruturados

---

## 📋 Requisitos de Hardware

Para melhor performance:

* **RAM:** 16 GB (mínimo)
* **GPU (recomendado):** NVIDIA com CUDA | 8 GB+ VRAM
* **Armazenamento:** ~15 GB livres

⚠️ *Sem GPU, o sistema funciona, mas com performance reduzida.*

---

## 🛠️ Requisitos de Software

* Python 3.10+
* Ollama (rodando em http://localhost:11434)
* Neo4j 5.x
* pip / virtualenv

---

## ⚙️ Configuração (.env)

Crie um arquivo `.env` na raiz:

```bash
cp .env.example .env
🔌 Conexões
NEO4J_URI=bolt://localhost:7687

NEO4J_USER=neo4j

NEO4J_PASSWORD=password

OLLAMA_URL=http://localhost:11434

🧠 Modelos
OLLAMA_FAST_MODEL=qwen2.5-coder:1.5b

OLLAMA_CHAT_MODEL=qwen3.5:4b

OLLAMA_COMPLEX_MODEL=qwen3-coder-next:q4_K_M

OLLAMA_EMBED_MODEL=nomic-embed-text

🧩 Persistência
RAG_INDEX_FILE=rag_index.json

RAG_STORE_FILE=rag_store.db

STATE_DB_FILE=insightgraph_state.db

QUALITY_HISTORY_FILE=quality_gate_history.json

QUALITY_HISTORY_LIMIT=20

⚡ GPU
OLLAMA_FORCE_GPU=false

OLLAMA_NUM_GPU=999

Notas:

OLLAMA_FORCE_GPU: força uso de GPU mesmo em fallback

OLLAMA_NUM_GPU: limite de GPUs (999 = auto)

🎨 Relatórios
REPORT_PROJECT_NAME=InsightGraph

REPORT_LOGO_TEXT=InsightGraph

🚀 Instalação e Execução
Instalar dependências

Bash
pip install -r requirements.txt
Baixar modelos (Ollama)

Bash
ollama pull qwen2.5-coder:1.5b
ollama pull qwen3.5:4b
ollama pull qwen3-coder-next:q4_K_M
ollama pull nomic-embed-text
Subir Neo4j
Certifique-se que está rodando em: bolt://localhost:7687

Executar análise

Bash
python main.py
🗄️ Estrutura de Dados
📦 RAG Store
rag_store.db: embeddings e contexto

rag_index.json: índice semântico

🧠 Estado
insightgraph_state.db: controle incremental

📊 Qualidade
quality_gate_history.json: histórico de execuções

🕸️ Modelo de Grafo
Exemplo de entidades:

📁 Arquivo

🧱 Classe

🔧 Função

Exemplo de relações:

CALLS

IMPORTS

DEPENDS_ON

EXTENDS

📊 Casos de Uso
Auditoria de código legado

Onboarding de novos devs

Engenharia reversa de sistemas

Documentação automática

Análise de impacto de mudanças

⚠️ Limitações
Projetos muito grandes podem exigir tuning

Dependência de GPU para melhor performance

Qualidade depende dos modelos locais
