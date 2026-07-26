FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY media_service/pyproject.toml ./
COPY media_service ./media_service
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "media_service.app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
