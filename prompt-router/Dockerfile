FROM python:3.10-slim
WORKDIR /app
COPY . .
RUN pip install fastapi uvicorn httpx
# Allow overriding the exposed port using the PORT env var
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8009}"]
