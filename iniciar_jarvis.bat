@echo off
rem Inicia o JARVIS: backend + HUD em janela de app (sem barra de endereco).
rem Duplo clique ou atalho na area de trabalho. Rode na sua sessao do Windows (nao como servico).
setlocal EnableExtensions
cd /d "%~dp0"
title JARVIS - backend

rem 1) HUD compilado: na primeira vez ou quando faltar alguma biblioteca, como o three do nucleo 3D.
rem    Depois de mudar o frontend, apague frontend\dist para recompilar.
set NEED_BUILD=0
if not exist "frontend\dist\index.html" set NEED_BUILD=1
if not exist "frontend\node_modules\three\package.json" set NEED_BUILD=1
if "%NEED_BUILD%"=="1" (
  echo [JARVIS] Compilando o HUD...
  pushd frontend
  call npm install
  call npm run build
  popd
)

cd backend
set "PY=.venv\Scripts\python.exe"

rem 2) Ambiente Python. O .venv que vem no Git foi criado em outra maquina e nao funciona aqui.
if exist "%PY%" (
  "%PY%" -c "import pydantic_core, fastapi, uvicorn" >nul 2>&1
  if errorlevel 1 (
    echo [JARVIS] O ambiente Python esta quebrado ou veio de outra maquina. Recriando...
    rmdir /s /q .venv
  )
)
if not exist "%PY%" (
  echo [JARVIS] Criando o ambiente Python - leva alguns minutos na primeira vez...
  py -3.12 -m venv .venv 2>nul
  if not exist "%PY%" py -3 -m venv .venv
)
if not exist "%PY%" (
  echo [JARVIS] Nao achei o Python. Instale o Python 3.12 em python.org e rode de novo.
  pause
  exit /b 1
)

echo [JARVIS] Conferindo dependencias...
"%PY%" -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo [JARVIS] Falha ao instalar as dependencias. Leia a mensagem acima.
  pause
  exit /b 1
)
"%PY%" -m pip install -q -r requirements-voz.txt
if errorlevel 1 (
  echo [JARVIS] AVISO: nao consegui instalar a voz livre, o faster-whisper. O Jarvis abre sem ela.
  echo [JARVIS] Se o seu Python for o 3.14, instale o 3.12 e apague a pasta backend\.venv.
)

rem 3) Sobe o backend - so aceita conexoes desta maquina - e abre o HUD em modo app
set JARVIS_OPEN_HUD=1
"%PY%" -m uvicorn main:app --host 127.0.0.1 --port 8000
pause
