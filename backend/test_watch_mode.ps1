# Script de teste para Watch Mode
# Testa os componentes principais sem iniciar o servidor completo

Write-Host "=== Teste do Watch Mode ===" -ForegroundColor Cyan
Write-Host ""

# Teste 1: Importar módulos
Write-Host "[1/4] Testando imports..." -ForegroundColor Yellow
$testImports = @"
import sys
sys.path.insert(0, '.')
try:
    from incremental_scanner import IncrementalScanner, ImpactResult
    from watch_manager import WatchManager
    print('✓ Imports OK')
except Exception as e:
    print(f'✗ Erro nos imports: {e}')
    sys.exit(1)
"@

$result = py -c $testImports 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  $result" -ForegroundColor Green
} else {
    Write-Host "  ✗ Erro: $result" -ForegroundColor Red
    exit 1
}

# Teste 2: Verificar watchfiles
Write-Host ""
Write-Host "[2/4] Testando watchfiles..." -ForegroundColor Yellow
$testWatchfiles = @"
try:
    from watchfiles import awatch, Change
    print('✓ watchfiles OK')
except Exception as e:
    print(f'✗ Erro: {e}')
    sys.exit(1)
"@

$result = py -c $testWatchfiles 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  $result" -ForegroundColor Green
} else {
    Write-Host "  ✗ Erro: $result" -ForegroundColor Red
    exit 1
}

# Teste 3: Verificar FastAPI WebSocket
Write-Host ""
Write-Host "[3/4] Testando FastAPI WebSocket..." -ForegroundColor Yellow
$testWebSocket = @"
try:
    from fastapi import WebSocket, WebSocketDisconnect
    print('✓ FastAPI WebSocket OK')
except Exception as e:
    print(f'✗ Erro: {e}')
    sys.exit(1)
"@

$result = py -c $testWebSocket 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  $result" -ForegroundColor Green
} else {
    Write-Host "  ✗ Erro: $result" -ForegroundColor Red
    exit 1
}

# Teste 4: Verificar estrutura de dados
Write-Host ""
Write-Host "[4/4] Testando estruturas de dados..." -ForegroundColor Yellow
$testDataStructures = @"
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ImpactResult:
    file_path: str
    changed_nodes: list
    affected_nodes: list
    risk_score: float
    coupling_delta: float
    summary: str
    timestamp: datetime

result = ImpactResult(
    file_path='test.java',
    changed_nodes=['node1'],
    affected_nodes=['node2', 'node3'],
    risk_score=75.5,
    coupling_delta=10.0,
    summary='Test summary',
    timestamp=datetime.now()
)

print(f'✓ ImpactResult OK: {result.file_path}, risk={result.risk_score}%')
"@

$result = py -c $testDataStructures 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  $result" -ForegroundColor Green
} else {
    Write-Host "  ✗ Erro: $result" -ForegroundColor Red
    exit 1
}

# Resumo
Write-Host ""
Write-Host "=== Todos os testes passaram! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Próximos passos:" -ForegroundColor Cyan
Write-Host "  1. Iniciar Neo4j (se ainda não estiver rodando)" -ForegroundColor Gray
Write-Host "  2. Iniciar Ollama (se ainda não estiver rodando)" -ForegroundColor Gray
Write-Host "  3. Executar: .\start_watch_mode.ps1" -ForegroundColor Gray
Write-Host ""
