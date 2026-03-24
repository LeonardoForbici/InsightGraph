# Monitor CodeQL Database Creation Progress
# Usage: .\monitor_codeql.ps1

$dbPath = "C:\git\InsightGraph\backend\codeql_databases\meuprojeto-db"
$sourceSize = 150  # MB
$estimatedFinalSize = 300  # MB (2x source size)
$startTime = Get-Date

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  CodeQL Database Creation Monitor" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Diretório: $dbPath" -ForegroundColor Yellow
Write-Host "Tamanho fonte: $sourceSize MB" -ForegroundColor Yellow
Write-Host "Tamanho estimado final: $estimatedFinalSize MB" -ForegroundColor Yellow
Write-Host ""
Write-Host "Monitorando a cada 5 segundos... (Ctrl+C para parar)" -ForegroundColor Green
Write-Host ""

$lastSize = 0
$iteration = 0

while ($true) {
    $iteration++
    $currentTime = Get-Date
    $elapsed = $currentTime - $startTime
    
    # Check if database exists
    if (Test-Path $dbPath) {
        # Calculate size
        $size = (Get-ChildItem $dbPath -Recurse -ErrorAction SilentlyContinue | 
                 Measure-Object -Property Length -Sum).Sum / 1MB
        $sizeRounded = [math]::Round($size, 2)
        
        # Calculate progress
        $progress = [math]::Round(($size / $estimatedFinalSize) * 100, 1)
        
        # Calculate growth rate (per second, then convert to per minute)
        $growth = $sizeRounded - $lastSize
        $growthRatePerSec = if ($iteration -gt 1) { $growth / 5 } else { 0 }
        $growthRate = [math]::Round($growthRatePerSec * 60, 2)
        
        # Estimate time remaining
        if ($growthRatePerSec -gt 0) {
            $remainingSec = ($estimatedFinalSize - $sizeRounded) / $growthRatePerSec
            $remainingMin = [math]::Round($remainingSec / 60, 1)
            $eta = "~$remainingMin min"
        } else {
            $eta = "Calculando..."
        }
        
        # Display progress
        Write-Host "[$($currentTime.ToString('HH:mm:ss'))] " -NoNewline -ForegroundColor Gray
        Write-Host "Tamanho: " -NoNewline
        Write-Host "$sizeRounded MB " -NoNewline -ForegroundColor Green
        Write-Host "| Progresso: " -NoNewline
        Write-Host "$progress% " -NoNewline -ForegroundColor Cyan
        Write-Host "| Crescimento: " -NoNewline
        Write-Host "+$growth MB " -NoNewline -ForegroundColor Yellow
        Write-Host "($growthRate MB/min) " -NoNewline -ForegroundColor Yellow
        Write-Host "| ETA: " -NoNewline
        Write-Host "$eta" -ForegroundColor Magenta
        
        # Check if complete
        if ($size -ge $estimatedFinalSize * 0.95) {
            Write-Host ""
            Write-Host "✅ Banco quase completo! Aguardando finalização..." -ForegroundColor Green
        }
        
        $lastSize = $sizeRounded
    } else {
        Write-Host "[$($currentTime.ToString('HH:mm:ss'))] " -NoNewline -ForegroundColor Gray
        Write-Host "⏳ Aguardando criação do diretório do banco..." -ForegroundColor Yellow
    }
    
    # Check if Java process is still running
    $javaProcess = Get-Process | Where-Object {$_.ProcessName -like "*java*" -and $_.CPU -gt 100}
    if (-not $javaProcess) {
        Write-Host ""
        Write-Host "⚠️  Nenhum processo Java com alta CPU detectado. Análise pode ter terminado ou falhado." -ForegroundColor Red
        Write-Host "Verifique o log do backend para mais detalhes." -ForegroundColor Red
        break
    }
    
    # Wait 5 seconds
    Start-Sleep -Seconds 5
}

Write-Host ""
Write-Host "Monitor encerrado." -ForegroundColor Cyan
