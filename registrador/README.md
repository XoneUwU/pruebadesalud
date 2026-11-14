# Registrador (MongoDB)

```
python registrador\mongo_local.py          arranca el MongoDB instalado, solo en 127.0.0.1 (datos en datos\mongo)
python registrador\registrador.py          guarda todo apto/# en la colección "mensajes"
python registrador\exportar.py             CSV por tipo en datos\exportes (para los gráficos de validación)
python registrador\reproducir.py --persona bri --sesiones     y luego --sesion o --desde/--hasta
python registrador\pruebas_registrador.py  prueba sin MongoDB ni MQTT
```

`iniciar.bat` abre MongoDB y el registrador justo después del broker. Todo está explicado en la sección 7
del README principal.
