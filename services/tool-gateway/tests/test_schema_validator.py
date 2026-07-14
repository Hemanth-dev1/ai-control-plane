"""Tests for schema validation and Kafka audit emission in the tool gateway."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.schema_validator import SchemaValidator
from shared_schemas.tool import ToolSchema


class TestSchemaValidator:
    """Tests for the SchemaValidator — validates tool arguments against JSON Schema."""

    def setup_method(self):
        self.validator = SchemaValidator()

    def test_valid_arguments_pass(self):
        """Valid arguments against a known schema should pass."""
        schema = ToolSchema(
            name="crm.lookup_customer",
            description="Look up a customer",
            input_schema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Customer ID"},
                },
                "required": ["customer_id"],
            },
            backend_service="crm-service",
        )
        is_valid, error = self.validator.validate(schema, {"customer_id": "CUST-001"})
        assert is_valid is True
        assert error is None

    def test_missing_required_field_fails(self):
        """Missing a required field should fail validation."""
        schema = ToolSchema(
            name="crm.lookup_customer",
            description="Look up a customer",
            input_schema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                },
                "required": ["customer_id"],
            },
            backend_service="crm-service",
        )
        is_valid, error = self.validator.validate(schema, {})
        assert is_valid is False
        assert "customer_id" in error

    def test_wrong_type_fails(self):
        """Passing a wrong type for a field should fail."""
        schema = ToolSchema(
            name="ticketing.create_ticket",
            description="Create a ticket",
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["title"],
            },
            backend_service="ticketing-service",
        )
        is_valid, error = self.validator.validate(schema, {"title": 123})
        assert is_valid is False
        assert error is not None

    def test_invalid_enum_value_fails(self):
        """An invalid enum value should fail validation."""
        schema = ToolSchema(
            name="ticketing.create_ticket",
            description="Create a ticket",
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["title"],
            },
            backend_service="ticketing-service",
        )
        is_valid, error = self.validator.validate(
            schema, {"title": "Bug", "priority": "urgent"}
        )
        assert is_valid is False

    def test_empty_schema_passes(self):
        """If schema has no input_schema, validation should pass."""
        schema = ToolSchema(
            name="test.tool",
            description="Test",
            input_schema={},
            backend_service="test-service",
        )
        is_valid, error = self.validator.validate(schema, {"anything": "goes"})
        assert is_valid is True

    def test_extra_fields_allowed_by_default(self):
        """Extra fields not in the schema should be allowed (no additionalProperties: false)."""
        schema = ToolSchema(
            name="crm.lookup_customer",
            description="Test",
            input_schema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                },
                "required": ["customer_id"],
            },
            backend_service="crm-service",
        )
        is_valid, error = self.validator.validate(
            schema, {"customer_id": "CUST-001", "extra_field": "should be allowed"}
        )
        assert is_valid is True

    def test_minimum_length_validation(self):
        """String minimum length should be validated if specified in schema."""
        schema = ToolSchema(
            name="crm.add_note",
            description="Add a note",
            input_schema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "minLength": 5},
                    "note": {"type": "string", "minLength": 1},
                },
                "required": ["customer_id", "note"],
            },
            backend_service="crm-service",
        )
        is_valid, error = self.validator.validate(
            schema, {"customer_id": "CUST-001", "note": ""}
        )
        assert is_valid is False


class TestSchemaValidatorEdgeCases:
    """Edge cases for the schema validator."""

    def setup_method(self):
        self.validator = SchemaValidator()

    def test_none_arguments_with_schema(self):
        """None arguments against a non-empty schema should fail gracefully."""
        validator = SchemaValidator()
        schema = ToolSchema(
            name="test.tool",
            description="Test",
            input_schema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                },
                "required": ["customer_id"],
            },
            backend_service="test-service",
        )
        is_valid, error = validator.validate(schema, None)
        # None should not validate against an object schema
        assert is_valid is False
        assert error is not None

    def test_complex_nested_schema(self):
        """Nested objects in schema should validate correctly."""
        schema = ToolSchema(
            name="test.complex",
            description="Test complex schema",
            input_schema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["field", "value"],
                    },
                },
                "required": ["filter"],
            },
            backend_service="test-service",
        )
        is_valid, error = self.validator.validate(
            schema, {"filter": {"field": "status", "value": "active"}}
        )
        assert is_valid is True
        assert error is None

    def test_invalid_nested_schema(self):
        """Invalid nested objects should fail."""
        validator = SchemaValidator()
        schema = ToolSchema(
            name="test.complex",
            description="Test",
            input_schema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                        },
                        "required": ["field"],
                    },
                },
                "required": ["filter"],
            },
            backend_service="test-service",
        )
        is_valid, error = validator.validate(schema, {"filter": {}})
        assert is_valid is False
