FROM python:3.12-slim

WORKDIR /app

# Install dependencies, including docker cli so qlever script can control containers
RUN apt-get update && apt-get install -y docker.io curl jq

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

# Create directories for processing
RUN mkdir -p /app/incoming /app/processed

COPY . .

# Run the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
