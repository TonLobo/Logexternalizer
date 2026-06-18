@echo off
title Build LogsSAJ.exe
cd /d "%~dp0"
color 0A

echo.
echo  ============================================
echo   Gerando LogsSAJ.exe - SAJ / Softplan
echo  ============================================
echo.

:: Verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo  [ERRO] Python nao encontrado. Instale antes de compilar.
    pause & exit /b 1
)

:: Instala PyInstaller
echo  [1/3] Instalando PyInstaller...
python -m pip install pyinstaller --quiet --disable-pip-version-check
if errorlevel 1 ( color 0C & echo  [ERRO] Falha ao instalar PyInstaller. & pause & exit /b 1 )

:: Remove builds anteriores
if exist "dist"  rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "LogsSAJ.spec" del /q "LogsSAJ.spec"

:: Compila
echo  [2/3] Compilando (pode levar 1-2 minutos)...
python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name LogsSAJ ^
    --add-data "version.txt;." ^
    launcher.py

if not exist "dist\LogsSAJ.exe" (
    color 0C
    echo.
    echo  [ERRO] Build falhou. Verifique as mensagens acima.
    pause & exit /b 1
)

:: Copia para raiz
echo  [3/3] Copiando executavel...
copy /y "dist\LogsSAJ.exe" "LogsSAJ.exe" >nul

:: Limpa temporarios
rmdir /s /q "dist"
rmdir /s /q "build"
del /q "LogsSAJ.spec" 2>nul

echo.
echo  ============================================
echo   [OK] LogsSAJ.exe gerado com sucesso!
echo  ============================================
echo.
echo  Proximos passos:
echo  1. Configure update_config.txt com o caminho do servidor de atualizacoes.
echo  2. Rode publicar.bat para gerar o pacote de distribuicao.
echo  3. Distribua a pasta "distribuicao\" para os usuarios.
echo.
pause
