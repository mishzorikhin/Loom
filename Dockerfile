FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

ENV SIM_DB=/data/sim.db \
    LLM_BASE_URL=http://192.168.0.16:8080/v1 \
    LLM_MODEL=qwen3.5-9b \
    LLM_TIMEOUT=60

EXPOSE 8421
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8421"]
