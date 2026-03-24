@echo off
echo ========================================
echo Creating CodeQL Database for meuponto-api
echo ========================================
echo.

cd /d C:\git\InsightGraph

echo Step 1: Creating CodeQL database...
codeql database create codeql-db-meuponto ^
  --language=java ^
  --source-root="c:\Users\forbi\OneDrive\Documents\GitHub\meuponto-api" ^
  --overwrite

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Failed to create CodeQL database
    echo.
    echo Common issues:
    echo - Java not found: Make sure JAVA_HOME is set
    echo - Build failed: Try adding --command="mvn clean compile"
    pause
    exit /b 1
)

echo.
echo ========================================
echo SUCCESS! Database created at: codeql-db-meuponto
echo ========================================
echo.
echo Next steps:
echo 1. Run analysis: codeql database analyze codeql-db-meuponto security-extended --format=sarif-latest --output=results.sarif
echo 2. Or use the API: curl -X POST http://localhost:8000/api/codeql/analyze -d "{\"database_path\": \"./codeql-db-meuponto\"}"
echo.
pause
