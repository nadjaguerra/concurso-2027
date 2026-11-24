@echo off
chcp 65001 >nul
echo ============================================================================
echo   PLATAFORMA INTELIGENTE DE PREPARACAO PARA CONCURSOS 2027
echo   Eixo 1: SEFAZ-PE (60%%) ^| Eixo 2: ANPD + Dados e TI (40%%)
echo   Acesse no navegador: http://127.0.0.1:8000
echo ============================================================================
cd /d "%~dp0"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
