"""Mock CRM service — Postgres-backed customer management."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

app = FastAPI(title="CRM Service", version="0.1.0")

# In-memory store for demo (replace with Postgres in production)
customers: dict[str, dict] = {}
notes: dict[str, list[dict]] = {}

# Seed with sample data
SEED_CUSTOMERS = {
    "CUST-001": {
        "id": "CUST-001",
        "name": "Acme Corporation",
        "email": "contact@acme.com",
        "tier": "premium",
        "status": "active",
        "created_at": "2024-01-15T10:00:00Z",
    },
    "CUST-002": {
        "id": "CUST-002",
        "name": "Globex Industries",
        "email": "info@globex.com",
        "tier": "standard",
        "status": "active",
        "created_at": "2024-03-20T14:30:00Z",
    },
    "CUST-003": {
        "id": "CUST-003",
        "name": "Initech Solutions",
        "email": "support@initech.com",
        "tier": "basic",
        "status": "suspended",
        "created_at": "2024-06-10T09:15:00Z",
    },
}
customers.update(SEED_CUSTOMERS)


class CustomerNote(BaseModel):
    note: str


class Note(BaseModel):
    id: str
    customer_id: str
    note: str
    created_at: datetime


@app.on_event("startup")
async def startup():
    logger.info("crm_service_started")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "crm-service"}


@app.get("/customers/{customer_id}")
async def get_customer(customer_id: str):
    """Look up a customer by ID."""
    customer = customers.get(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
    return customer


@app.post("/customers/{customer_id}/notes")
async def add_note(customer_id: str, note: CustomerNote):
    """Add a note to a customer record."""
    if customer_id not in customers:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")

    if customer_id not in notes:
        notes[customer_id] = []

    note_record = {
        "id": str(uuid.uuid4()),
        "customer_id": customer_id,
        "note": note.note,
        "created_at": datetime.utcnow().isoformat(),
    }
    notes[customer_id].append(note_record)

    logger.info("note_added", customer_id=customer_id, note_id=note_record["id"])
    return note_record


@app.get("/customers/{customer_id}/notes")
async def get_notes(customer_id: str):
    """Get all notes for a customer."""
    return notes.get(customer_id, [])
