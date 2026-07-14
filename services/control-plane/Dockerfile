FROM python:3.11-slim

WORKDIR /app

# Install the shared schemas package
COPY libs/shared_schemas/ /app/libs/shared_schemas/
RUN pip install -e /app/libs/shared_schemas/

# Install service dependencies
COPY services/control-plane/requirements.txt /app/services/control-plane/
RUN pip install -r /app/services/control-plane/requirements.txt

# Copy service code
COPY services/control-plane/app/ /app/services/control-plane/app/

ENV PYTHONPATH="/app/services/control-plane:/app/libs/shared_schemas:$PYTHONPATH"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
