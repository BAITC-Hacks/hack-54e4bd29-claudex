FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=2
COPY pilot/requirements.txt /app/pilot/requirements.txt
RUN pip install --no-cache-dir -r pilot/requirements.txt && useradd --uid 1001 --create-home medsignal
COPY ml /app/ml
COPY pilot /app/pilot
USER medsignal
CMD ["uvicorn", "pilot.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
