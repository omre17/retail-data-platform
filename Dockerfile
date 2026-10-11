FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY sql/ ./sql/

CMD ["python", "-m", "src.run_pipeline"]
