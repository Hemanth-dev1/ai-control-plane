FROM python:3.11-slim

WORKDIR /app

# Install shared schemas
COPY libs/shared_schemas/ /app/libs/shared_schemas/
RUN pip install -e /app/libs/shared_schemas/

# Install dependencies
COPY services/agent-runtime/requirements.txt /app/services/agent-runtime/
RUN pip install -r /app/services/agent-runtime/requirements.txt

# Copy service code
COPY services/agent-runtime/app/ /app/services/agent-runtime/app/

ENV PYTHONPATH="/app/services/agent-runtime:/app/libs/shared_schemas:$PYTHONPATH"

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
