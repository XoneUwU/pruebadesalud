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

rem ---- MongoDB (solo en esta laptop, 127.0.0.1) y registrador de todo apto/# ----
start "MongoDB" cmd /k %PY% registrador\mongo_local.py
start "Registrador" cmd /k %PY% registrador\registrador.py

rem ---- Modulos de Bri ----
start "Voz" cmd /k %PY% voz\voz_fatiga.py --servicio
start "Copiloto" cmd /k %PY% copiloto\copiloto.py

rem ---- Coordinador: el provisional hasta que este el de Danilo ----
rem Cuando exista coordinador\coordinador.py: poner "rem" al provisional y quitarlo al de Danilo.
start "Coordinador provisional" cmd /k %PY% coordinador\coordinador_provisional.py
rem start "Coordinador" cmd /k %PY% coordinador\coordinador.py

rem ---- Vision (abre su ventana sola al medir) y paneles ----
start "Vision" cmd /k %PY% vision\vision.py --servicio
start "Paneles" cmd /k %PY% paneles\servidor.py

rem ---- Para probar sin los demas modulos ----
rem start "Simulador" cmd /k %PY% herramientas\simulador.py

echo Sistema iniciado. Cada modulo tiene su propia ventana.
echo Paneles: http://localhost:8080  (desde otra laptop: http://IP-de-esta-laptop:8080/tripulacion.html)
