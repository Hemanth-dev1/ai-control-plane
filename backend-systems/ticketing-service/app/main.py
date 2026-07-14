"""Mock ticketing service — support ticket management."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

app = FastAPI(title="Ticketing Service", version="0.1.0")

# In-memory store
tickets: dict[str, dict] = {}
SEED_ID = str(uuid.uuid4())
tickets[SEED_ID] = {
    "id": SEED_ID,
    "title": "Unable to access billing portal",
    "description": "Customer reports 403 error when accessing billing section",
    "status": "open",
    "priority": "high",
    "customer_id": "CUST-001",
    "created_at": datetime.utcnow().isoformat(),
    "updated_at": datetime.utcnow().isoformat(),
}


class TicketCreate(BaseModel):
    title: str
    description: str
    priority: str = "medium"
    customer_id: Optional[str] = None


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@app.on_event("startup")
async def startup():
    logger.info("ticketing_service_started")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "ticketing-service"}


@app.post("/tickets")
async def create_ticket(ticket: TicketCreate):
    """Create a new support ticket."""
    if ticket.priority not in ["low", "medium", "high", "critical"]:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {ticket.priority}")

    ticket_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    ticket_record = {
        "id": ticket_id,
        "title": ticket.title,
        "description": ticket.description,
        "status": "open",
        "priority": ticket.priority,
        "customer_id": ticket.customer_id,
        "created_at": now,
        "updated_at": now,
    }

    tickets[ticket_id] = ticket_record

    logger.info("ticket_created", ticket_id=ticket_id, priority=ticket.priority)
    return ticket_record


@app.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: str):
    """Get a ticket by ID."""
    ticket = tickets.get(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return ticket


@app.get("/tickets")
async def list_tickets(status: Optional[str] = None):
    """List all tickets, optionally filtered by status."""
    if status:
        return [t for t in tickets.values() if t["status"] == status]
    return list(tickets.values())
