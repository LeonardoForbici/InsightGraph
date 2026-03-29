<# 
    reset-insightgraph-state.ps1
    =============================
    Apaga o estado persistido (SQLite + RAG) para reiniciar o InsightGraph do zero.
    O script NÃO tenta parar o backend; garanta que a API/Neo4j/Ollama estejam desligados
    antes de executá-lo para evitar corrupção de arquivos.

    Uso:
      ./scripts/reset-insightgraph-state.ps1       # remove os arquivos principais com confirmação
      ./scripts/reset-insightgraph-state.ps1 -Force  # ignora o prompt de confirmação

    O script remove:
      * backend/insightgraph_state.db      (estado, views, tags, anotações)
      * backend/rag_store.db               (embeddings armazenadas)
      * backend/rag_index.json             (índice de nós do RAG)

    Você pode recriar o ambiente com um novo scan; os arquivos serão recriados automaticamente.
#>
[CmdletBinding()]
param(
    [switch]$Force
)


function Confirm-Delete {
    param([string]$Target)
    if ($Force) { return $true }
    $response = Read-Host "Deseja realmente remover $Target? (s/n)"
    return $response -match '^[sS]$'
}

$filesToRemove = @(
    "backend\insightgraph_state.db",
    "backend\rag_store.db",
    "backend\rag_index.json"
)

$deleted = @()
$skipped = @()

foreach ($relativePath in $filesToRemove) {
    $fullPath = Join-Path (Get-Location) $relativePath
    if (-not (Test-Path $fullPath)) {
        $skipped += $relativePath
        continue
    }
    if (-not (Confirm-Delete $relativePath)) {
        $skipped += $relativePath
        continue
    }
    try {
        Remove-Item -LiteralPath $fullPath -Force
        $deleted += $relativePath
    } catch {
        Write-Warning "Falha ao remover ${relativePath}: $_"
        $skipped += $relativePath
    }
}

Write-Host "Reset concluído."
if ($deleted) {
    Write-Host "Arquivos removidos:"
    $deleted | ForEach-Object { Write-Host "  - $_" }
}
if ($skipped) {
    Write-Host "Arquivos ignorados (não existiam ou confirmação negada):"
    $skipped | ForEach-Object { Write-Host "  - $_" }
}
Write-Host "`nLembre-se de reiniciar a API (uvicorn) e o Neo4j antes de iniciar um novo scan."
