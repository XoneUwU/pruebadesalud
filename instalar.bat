@echo off
rem Instala todo lo necesario para la voz y el copiloto. Ejecutar una sola vez.
cd /d %~dp0

echo [1/5] Buscando Python 3.11 o 3.12...
set "PYEXE="
py -3.11 --version >nul 2>&1 && set "PYEXE=py -3.11"
if not defined PYEXE (py -3.12 --version >nul 2>&1 && set "PYEXE=py -3.12")
if not defined PYEXE (
  for /f "tokens=2" %%v in ('python --version 2^>nul') do (
    echo %%v| findstr /b "3.11 3.12" >nul && set "PYEXE=python"
  )
)
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PYEXE="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set PYEXE="%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PYEXE (echo No se encontro Python 3.11 ni 3.12. Instala uno desde python.org & pause & exit /b 1)
echo Usando: %PYEXE%
%PYEXE% -m venv .venv || (echo No se pudo crear el entorno & pause & exit /b 1)
.venv\Scripts\python -m pip install --upgrade pip

echo [2/5] Instalando librerias...
.venv\Scripts\pip install -r voz\requirements.txt -r copiloto\requirements.txt -r registrador\requirements.txt || (echo Fallo la instalacion de librerias & pause & exit /b 1)

echo [3/5] Instalando Piper (voz natural). Si falla, se usara la voz de Windows...
.venv\Scripts\pip install piper-tts || echo AVISO: Piper no se instalo; el copiloto usara la voz de Windows.

echo [4/5] Descargando la voz en espanol de Piper...
if not exist modelos mkdir modelos
curl -L -o modelos\es_MX-ald-medium.onnx https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/ald/medium/es_MX-ald-medium.onnx
curl -L -o modelos\es_MX-ald-medium.onnx.json https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/ald/medium/es_MX-ald-medium.onnx.json

echo [5/5] Descargando modelos de IA (puede tardar)...
set "OLLAMA=ollama"
where ollama >nul 2>&1 || if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set OLLAMA="%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
%OLLAMA% pull qwen2.5:7b || echo AVISO: no se pudo usar Ollama. Abre la app de Ollama y vuelve a intentar.
.venv\Scripts\python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8'); print('Whisper listo')"

echo.
echo Instalacion terminada.
pause
