FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY deploy/d1/requirements.lock /app/requirements.lock
RUN python -m pip install --no-cache-dir -r /app/requirements.lock

COPY src /app/src
COPY sql/postgres /app/sql/postgres
COPY deploy/__init__.py /app/deploy/__init__.py
COPY deploy/d1/__init__.py deploy/d1/entrypoint.py /app/deploy/d1/

USER 10001:10001
ENTRYPOINT ["python", "-m", "deploy.d1.entrypoint"]
CMD ["serve"]
