FROM python:3.11-slim

WORKDIR /app

# Install shared schemas
COPY libs/shared_schemas/ /app/libs/shared_schemas/
RUN pip install -e /app/libs/shared_schemas/

# Install dependencies
COPY services/tool-gateway/requirements.txt /app/services/tool-gateway/
RUN pip install -r /app/services/tool-gateway/requirements.txt

# Copy service code
COPY services/tool-gateway/app/ /app/services/tool-gateway/app/

ENV PYTHONPATH="/app/services/tool-gateway:/app/libs/shared_schemas:$PYTHONPATH"

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
