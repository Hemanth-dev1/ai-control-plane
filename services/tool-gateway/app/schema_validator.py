"""Schema validation for tool invocations — validates arguments against JSON Schema."""

from __future__ import annotations

from typing import Any

import structlog
from jsonschema import ValidationError, validate as jsonschema_validate

from shared_schemas.tool import ToolSchema

logger = structlog.get_logger(__name__)


class SchemaValidator:
    """Validates tool invocation arguments against the tool's JSON Schema."""

    def validate(self, tool_schema: ToolSchema, arguments: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate arguments against the tool schema.

        Returns (is_valid, error_message).
        """
        input_schema = tool_schema.input_schema
        if not input_schema:
            return True, None

        try:
            jsonschema_validate(instance=arguments, schema=input_schema)
            return True, None
        except ValidationError as e:
            error_msg = f"Validation failed for '{tool_schema.name}': {e.message}"
            logger.warning("schema_validation_failed", tool=tool_schema.name, error=e.message)
            return False, error_msg
