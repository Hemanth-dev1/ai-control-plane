package control_plane

# =============================================================================
# OPA Policy: Enterprise AI Control Plane Authorization
# =============================================================================
# Rules:
# 1. Agent must be active
# 2. Tool must be in agent's allowed scopes
# 3. Special rules for high-risk operations (e.g., large amounts, high-priority tickets)

import future.keywords

# Default deny
default allow = false
default deny_reason = "Action denied: no matching policy"

# =============================================================================
# Allow rules
# =============================================================================

# Rule 1: Agent is allowed to call any tool in its allowed scopes
allow {
    tool_in_allowed_scopes
    not high_risk_operation
}

# Rule 2: Allow high-risk operations if they pass additional checks
allow {
    tool_in_allowed_scopes
    high_risk_operation
    passes_additional_checks
}

# =============================================================================
# Helper rules
# =============================================================================

# Check if the requested tool is in the agent's allowed scopes
tool_in_allowed_scopes {
    # In a real system, the agent's scopes would come from the control plane DB
    # For this demo, we check known agent patterns
    input.tool_name == "crm.lookup_customer"
}

tool_in_allowed_scopes {
    input.tool_name == "crm.add_note"
}

tool_in_allowed_scopes {
    input.tool_name == "ticketing.create_ticket"
}

tool_in_allowed_scopes {
    input.tool_name == "ticketing.get_ticket"
}

tool_in_allowed_scopes {
    input.tool_name == "notify.send_message"
}

# High-risk operations that need additional checks
high_risk_operation {
    input.tool_name == "crm.add_note"
}

high_risk_operation {
    input.tool_name == "notify.send_message"
}

# Additional checks for high-risk operations
passes_additional_checks {
    input.tool_name == "crm.add_note"
    # Only allow notes that are not empty and not too long
    note := input.arguments.note
    count(note) > 0
    count(note) < 5000
}

passes_additional_checks {
    input.tool_name == "notify.send_message"
    # Only allow notifications to known recipients (basic validation)
    recipient := input.arguments.recipient
    contains(recipient, "@")
}

# =============================================================================
# Deny reasons (for audit logging)
# =============================================================================

deny_reason = "Action denied: agent not found or inactive" {
    not tool_in_allowed_scopes
}

deny_reason = "Action denied: high-risk operation failed additional checks" {
    tool_in_allowed_scopes
    high_risk_operation
    not passes_additional_checks
}

deny_reason = "Action denied: tool not recognized" {
    not tool_in_allowed_scopes
}
