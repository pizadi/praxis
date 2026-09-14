FROM python:3.12-slim

WORKDIR /srv

# Liara PyPI mirror (fast in Iran; harmless elsewhere). Override with
# --build-arg PIP_INDEX_URL=https://pypi.org/simple if undesired.
ARG PIP_INDEX_URL=https://package-mirror.liara.ir/repository/pypi/simple
COPY requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt

COPY app app
COPY alembic.ini .
COPY alembic alembic

# Run migrations then start; uploads dir comes from the mounted volume
ENV UPLOAD_DIR=/data/uploads
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
