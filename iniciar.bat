@echo off
title Logs Integracao SAJ
cd /d "%~dp0"
color 0A

echo.
echo  ============================================
echo   Logs Integracao SAJ - SAJ / Softplan
echo  ============================================
echo.

:: ── Verifica se Python esta instalado ─────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo  [ERRO] Python nao encontrado no computador.
    echo.
    echo  Para instalar o Python:
    echo  1. Abra o navegador e acesse: https://www.python.org/downloads/
    echo  2. Clique em "Download Python" e instale.
    echo  3. IMPORTANTE: marque a opcao "Add Python to PATH" na instalacao.
    echo  4. Apos instalar, feche e abra este arquivo novamente.
    echo.
    pause
    exit /b 1
)

echo  [OK] Python encontrado.
echo.

:: ── Instala / atualiza dependencias automaticamente ───────────────────────
echo  Verificando dependencias (apenas na primeira vez pode demorar)...
echo.
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    color 0C
    echo.
    echo  [ERRO] Falha ao instalar dependencias.
    echo  Verifique sua conexao com a internet e tente novamente.
    echo.
    pause
    exit /b 1
)

echo  [OK] Dependencias prontas.
echo.

:: ── Abre o navegador automaticamente apos 3 segundos ─────────────────────
echo  Iniciando o sistema...
echo.
echo  O navegador abrira automaticamente em instantes.
echo  Caso nao abra, acesse manualmente: http://localhost:8501
echo.
echo  Para encerrar o sistema, feche esta janela.
echo  ============================================
echo.

:: Aguarda 3s e abre o navegador em segundo plano
start "" /b cmd /c "timeout /t 3 >nul && start http://localhost:8501"

:: Inicia o Streamlit
python -m streamlit run app.py ^
    --server.port 8501 ^
    --server.headless false ^
    --browser.gatherUsageStats false ^
    --browser.serverAddress localhost

:: Se chegar aqui, o servidor encerrou
echo.
echo  O sistema foi encerrado.
pause
