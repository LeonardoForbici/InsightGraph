# Script PowerShell para iniciar o InsightGraph com Watch Mode
# Uso: .\start_watch_mode.ps1

Write-Host "=== InsightGraph Watch Mode ===" -ForegroundColor Cyan
Write-Host ""

# Verificar se Python está disponível
try {
    $pythonVersion = py --version 2>&1
    Write-Host "✓ Python encontrado: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python não encontrado. Instale Python 3.12+ primeiro." -ForegroundColor Red
    exit 1
}

# Verificar dependências
Write-Host ""
Write-Host "Verificando dependências..." -ForegroundColor Yellow

$dependencies = @("fastapi", "watchfiles", "httpx", "py2neo", "tree-sitter")
$missing = @()

foreach ($dep in $dependencies) {
    $installed = py -m pip show $dep 2>&1
    if ($LASTEXITCODE -ne 0) {
        $missing += $dep
    }
}

if ($missing.Count -gt 0) {
    Write-Host "✗ Dependências faltando: $($missing -join ', ')" -ForegroundColor Red
    Write-Host ""
    Write-Host "Instalando dependências..." -ForegroundColor Yellow
    py -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Erro ao instalar dependências" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "✓ Todas as dependências instaladas" -ForegroundColor Green
}

# Verificar Neo4j (opcional)
Write-Host ""
Write-Host "Verificando Neo4j..." -ForegroundColor Yellow
$neo4jUri = $env:NEO4J_URI
if (-not $neo4jUri) {
    $neo4jUri = "bolt://localhost:7687"
}
Write-Host "  URI: $neo4jUri" -ForegroundColor Gray

# Verificar Ollama (opcional)
Write-Host ""
Write-Host "Verificando Ollama..." -ForegroundColor Yellow
$ollamaUrl = $env:OLLAMA_URL
if (-not $ollamaUrl) {
    $ollamaUrl = "http://localhost:11434"
}
Write-Host "  URL: $ollamaUrl" -ForegroundColor Gray

# Iniciar servidor
Write-Host ""
Write-Host "=== Iniciando InsightGraph ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Servidor estará disponível em: http://localhost:8000" -ForegroundColor Green
Write-Host "Documentação da API: http://localhost:8000/docs" -ForegroundColor Green
Write-Host ""
Write-Host "Watch Mode endpoints:" -ForegroundColor Yellow
Write-Host "  POST /api/watch/start   - Iniciar monitoramento" -ForegroundColor Gray
Write-Host "  POST /api/watch/stop    - Parar monitoramento" -ForegroundColor Gray
Write-Host "  GET  /api/watch/status  - Status do monitoramento" -ForegroundColor Gray
Write-Host "  WS   /api/watch/ws/{path} - WebSocket para updates" -ForegroundColor Gray
Write-Host ""
Write-Host "Pressione Ctrl+C para parar o servidor" -ForegroundColor Yellow
Write-Host ""

# Executar servidor
py main.py serve
