FROM python:3.11-slim

WORKDIR /app

COPY backend-systems/ticketing-service/requirements.txt /app/
RUN pip install -r /app/requirements.txt

COPY backend-systems/ticketing-service/app/ /app/app/

EXPOSE 8004

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
