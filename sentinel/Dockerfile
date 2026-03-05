FROM python:3.11-slim
RUN useradd --create-home -u 1000 appuser
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py .
COPY prompts/ prompts/

USER appuser
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-u", "sentinel.py"]
