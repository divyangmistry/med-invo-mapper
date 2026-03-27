FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/db /app/outputs

ENV PYTHONUNBUFFERED=1

EXPOSE 8501
CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.port=8501", \
     "--browser.gatherUsageStats=false"]
