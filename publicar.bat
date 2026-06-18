@echo off
title Publicar Atualizacao - LogsSAJ
cd /d "%~dp0"
color 0B

echo.
echo  ============================================
echo   Publicar nova versao - SAJ / Softplan
echo  ============================================
echo.

:: ── Le versao atual ───────────────────────────────────────────────────────
set /p VERSAO_ATUAL=<version.txt
echo  Versao atual : %VERSAO_ATUAL%
set /p VERSAO_NOVA="  Nova versao  : "

if "%VERSAO_NOVA%"=="" (
    echo  [AVISO] Versao nao informada. Usando versao atual.
    set VERSAO_NOVA=%VERSAO_ATUAL%
)

:: ── Grava nova versao ─────────────────────────────────────────────────────
echo %VERSAO_NOVA%> version.txt
echo.
echo  [1/4] Versao atualizada para: %VERSAO_NOVA%

:: ── Gera ZIP de atualizacao ───────────────────────────────────────────────
echo.
echo  [2/4] Gerando pj-consultador-xml.zip...

python -c "
import zipfile, os
files = [
    'app.py','config.py','exporter.py','fetcher.py',
    'xml_parser.py','atualizador.py','requirements.txt',
    'manual.html','version.txt'
]
base = r'%~dp0'
with zipfile.ZipFile(os.path.join(base,'pj-consultador-xml.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
    for f in files:
        fp = os.path.join(base, f)
        if os.path.exists(fp):
            z.write(fp, f)
            print('  +', f)
        else:
            print('  ! NAO ENCONTRADO:', f)
print('ZIP gerado.')
"
if errorlevel 1 ( color 0C & echo [ERRO] Falha ao gerar ZIP. & pause & exit /b 1 )

:: ── Commit e push para o GitHub ───────────────────────────────────────────
echo.
echo  [3/4] Publicando no GitHub...

git add app.py config.py exporter.py fetcher.py xml_parser.py ^
        atualizador.py launcher.py requirements.txt manual.html ^
        version.txt update_config.txt build.bat publicar.bat ^
        iniciar.bat LogsSAJ.exe pj-consultador-xml.zip .gitignore 2>nul

git commit -m "release: versao %VERSAO_NOVA%"
if errorlevel 1 (
    echo  [INFO] Nenhuma mudanca para commitar ou erro no commit.
)

git push origin main
if errorlevel 1 (
    color 0C
    echo.
    echo  [ERRO] Falha no push. Verifique autenticacao do GitHub.
    pause & exit /b 1
)

:: ── Gera pasta de distribuicao para novos usuarios ────────────────────────
echo.
echo  [4/4] Gerando pasta distribuicao\...

if exist "distribuicao" rmdir /s /q "distribuicao"
mkdir "distribuicao"

for %%F in (LogsSAJ.exe update_config.txt manual.html version.txt ^
            app.py config.py exporter.py fetcher.py xml_parser.py ^
            atualizador.py requirements.txt) do (
    if exist "%%F" (
        copy /y "%%F" "distribuicao\" >nul
        echo   + %%F
    )
)

echo.
echo  ============================================
echo   [OK] Versao %VERSAO_NOVA% publicada no GitHub!
echo  ============================================
echo.
echo  Usuarios com o sistema instalado receberao a atualizacao
echo  automaticamente na proxima abertura do LogsSAJ.exe.
echo.
echo  Para novos usuarios: envie a pasta distribuicao\
echo.
pause
