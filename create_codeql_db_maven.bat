@echo off
echo ========================================
echo Creating CodeQL Database with Maven Build
echo ========================================
echo.

cd /d C:\git\InsightGraph

echo Checking Java...
java -version
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Java not found. Please install Java and set JAVA_HOME
    pause
    exit /b 1
)

echo.
echo Checking Maven...
mvn -version
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Maven not found. Please install Maven
    pause
    exit /b 1
)

echo.
echo Step 1: Creating CodeQL database with Maven build...
codeql database create codeql-db-meuponto ^
  --language=java ^
  --command="mvn clean compile -DskipTests" ^
  --source-root="c:\Users\forbi\OneDrive\Documents\GitHub\meuponto-api" ^
  --overwrite

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Failed to create CodeQL database
    pause
    exit /b 1
)

echo.
echo ========================================
echo SUCCESS! Database created at: codeql-db-meuponto
echo ========================================
echo.
pause
