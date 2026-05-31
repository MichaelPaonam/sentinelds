from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class SentinelDecision(BaseModel):
    """Represents a pre-flight decision made by the Sentinel Agent.

    SentinelDS intercepts agent tool execution and queries Dynatrace via MCP
    before deciding whether to ALLOW, HALT, or QUARANTINE the request.
    """

    decision: Literal["ALLOW", "HALT", "QUARANTINE"]
    reason: str
    rule_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    target_tool: str
    mcp_status: Literal["REACHABLE", "UNREACHABLE_FAIL_CLOSED", "UNREACHABLE_FAIL_OPEN"]
    span_id: Optional[str] = None


class SentinelPolicy(BaseModel):
    """The active security policy and rule set enforced by SentinelDS."""

    policy_id: str
    default_action: Literal["ALLOW", "HALT"] = "ALLOW"
    fail_closed: bool = True
    monitored_tools: List[str] = Field(
        default_factory=lambda: ["execute_code", "web_fetch", "model_train"]
    )
    drift_threshold: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Statistical drift threshold before triggering alert"
    )


class WorkspaceState(BaseModel):
    """Represents the real-time security state of the data-science workspace."""

    project_id: str
    location: str
    is_compromised: bool = False
    active_problems_count: int = 0
    quarantined_agents: List[str] = Field(default_factory=list)
