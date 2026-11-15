# Imagen de Houston: receptor.py (Mosquitto -> MongoDB) y servidor.py (web). Se construye desde la raíz del repo
# (docker-compose.yml lo hace): necesita comun/, registrador/almacen.py y config.env.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY houston/requirements.txt houston/requirements.txt
RUN pip install --no-cache-dir -r houston/requirements.txt

COPY config.env ./
COPY comun/ comun/
COPY registrador/almacen.py registrador/almacen.py
# El diseño de la estación (Nocturne, íconos, fuente, logo y fondo): la vista de Houston lo usa tal cual.
COPY paneles/web/nocturne.css paneles/web/app.css paneles/web/plantilla.js paneles/web/logo.js paneles/web/fondo.js paneles/web/
COPY paneles/web/vendor/phosphor/ paneles/web/vendor/phosphor/
COPY paneles/web/vendor/inter/ paneles/web/vendor/inter/
COPY houston/ houston/

EXPOSE 8090
CMD ["python", "houston/servidor.py"]
