@echo off
title Consultador XML - SAJ
cd /d "%~dp0"

echo Verificando dependencias...
python -m pip install -r requirements.txt --quiet

echo.
echo Iniciando Consultador XML...
echo Acesse: http://localhost:8501
echo.
python -m streamlit run app.py --server.port 8501 --server.headless false --browser.gatherUsageStats false
pause
