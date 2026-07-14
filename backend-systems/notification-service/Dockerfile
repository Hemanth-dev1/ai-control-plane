FROM python:3.11-slim

WORKDIR /app

COPY backend-systems/notification-service/requirements.txt /app/
RUN pip install -r /app/requirements.txt

COPY backend-systems/notification-service/app/ /app/app/

EXPOSE 8005

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
