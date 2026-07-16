FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY services/audit-consumer/requirements.txt .
RUN pip install -r requirements.txt

# Copy source
COPY services/audit-consumer/main.py ./main.py

CMD ["python", "main.py"]
