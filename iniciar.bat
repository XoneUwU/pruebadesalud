@echo off
rem Arranca el sistema completo en esta laptop.
rem   iniciar.bat        modo evento (con usuarios y permisos)
rem   iniciar.bat dev    modo desarrollo (sin usuarios)
cd /d %~dp0
set "MOSQ=C:\Program Files\mosquitto\mosquitto.exe"
set "PY=.venv\Scripts\python"

set "CONF=mosquitto\mosquitto.conf"
if /i "%1"=="dev" set "CONF=mosquitto\mosquitto-dev.conf"
if /i not "%1"=="dev" if not exist mosquitto\passwd (
  echo Falta mosquitto\passwd. Ejecuta primero mosquitto\crear_usuarios.bat
  pause & exit /b 1
)

sc query mosquitto | find "RUNNING" >nul && (
  echo El servicio de Mosquitto de Windows esta activo y ocupa el puerto 1883.
  echo Detenlo como administrador con:  net stop mosquitto
  pause & exit /b 1
)

echo Iniciando broker MQTT...
start "Broker MQTT" "%MOSQ%" -c %CONF% -v
timeout /t 2 >nul

rem ---- Modulos de Xone ----
start "Voz" cmd /k %PY% voz\voz_fatiga.py --servicio
start "Copiloto" cmd /k %PY% copiloto\copiloto.py

rem ---- Modulos del equipo: quitar "rem" cuando esten en esta laptop ----
rem start "Coordinador" cmd /k %PY% coordinador\coordinador.py
rem start "Vision" cmd /k %PY% vision\vision.py
rem start "Paneles" cmd /k %PY% paneles\servidor.py

rem ---- Para probar sin los demas modulos ----
rem start "Simulador" cmd /k %PY% herramientas\simulador.py

echo Sistema iniciado. Cada modulo tiene su propia ventana.
