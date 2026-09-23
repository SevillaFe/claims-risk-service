# =============================================================
# Multi-stage build
#  Etapa 1 (builder): instala dependencias y entrena el modelo.
#  Etapa 2 (runtime): solo copia lo necesario para ejecutar.
#  Resultado: imagen final más pequeña y con menos superficie de ataque
#  (sin compiladores, sin caché de pip, sin código de entrenamiento suelto).
# =============================================================

# ---------- Etapa 1: builder ----------
FROM python:3.12-slim AS builder

WORKDIR /build

# Virtualenv en una ruta fija para poder copiarlo entero a la etapa 2
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copiamos PRIMERO requirements.txt: si no cambia, Docker reutiliza la capa
# cacheada y no reinstala dependencias en cada build (builds mucho más rápidos).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ahora el código (cambia a menudo -> va después)
COPY app/ app/
RUN python -m app.train


# ---------- Etapa 2: runtime ----------
FROM python:3.12-slim AS runtime

# Usuario sin privilegios: si alguien compromete la app, no es root en el contenedor
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/app ./app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001
EXPOSE 8000

# Forma "exec" (array JSON): uvicorn es PID 1 y recibe SIGTERM para un apagado limpio
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
