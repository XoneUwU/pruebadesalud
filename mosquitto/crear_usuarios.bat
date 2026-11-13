@echo off
rem Crea los usuarios de MQTT. Te pedira la clave de cada uno.
cd /d %~dp0..
set "MOSQ_DIR=C:\Program Files\mosquitto"
echo Clave para el usuario "sistema" (la usan los programas y el ESP32):
"%MOSQ_DIR%\mosquitto_passwd.exe" -c mosquitto\passwd sistema
echo Clave para el usuario "equipo" (solo lectura, para ver la interfaz):
"%MOSQ_DIR%\mosquitto_passwd.exe" mosquitto\passwd equipo
echo Listo. Usuarios guardados en mosquitto\passwd
pause
