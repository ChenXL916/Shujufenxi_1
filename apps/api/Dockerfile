FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
COPY apps/api/pyproject.toml ./
COPY apps/api/app ./app
COPY apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
COPY config ./config
COPY fixtures ./fixtures
COPY scripts ./scripts
COPY apps/api/scripts/migrate_sqlite_to_postgres.py ./scripts/migrate_sqlite_to_postgres.py
RUN pip install --no-cache-dir .
RUN chown -R app:app /app
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
