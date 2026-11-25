# Imagen para desplegar Iron Coach (compatible con Hugging Face Spaces, puerto 7860).
FROM python:3.12-slim

# Hugging Face ejecuta el contenedor con el usuario 1000
RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PORT=7860 \
    FASTEMBED_CACHE_PATH=/home/user/.cache/fastembed \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    PYTHONUNBUFFERED=1

WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

# Ingesta en el build: descarga el modelo de embeddings y crea chroma_db una sola vez
RUN python -m app.ingesta

EXPOSE 7860
CMD ["python", "server.py"]
