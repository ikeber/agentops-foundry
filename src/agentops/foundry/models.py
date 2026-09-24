"""AgentOps-owned representations of Foundry data.

These types keep Foundry SDK objects out of the rest of AgentOps.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FoundryAgentVersion(BaseModel):
    """A specific, verified version of a Foundry agent.

    Foundry agent versions are immutable, so a test result attributed to one of these can be
    traced to exactly one agent configuration. It is obtained from
    :meth:`FoundryAgentClient.resolve_version`, and every invocation is pinned to one.
    """

    model_config = ConfigDict(frozen=True)

    agent_name: str
    version: str
    created_at: datetime
    draft: bool = False


class AgentInvocationResult(BaseModel):
    """The outcome of sending one input to a pinned Foundry agent version."""

    model_config = ConfigDict(frozen=True)

    agent: FoundryAgentVersion
    response_id: str
    status: str | None
    output_text: str
