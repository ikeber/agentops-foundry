"""Microsoft Foundry integration adapter (REQ-001).

This package is the only part of AgentOps that talks to the Foundry SDK.
"""

from agentops.foundry.client import FoundryAgentClient
from agentops.foundry.errors import (
    FoundryAgentNotFoundError,
    FoundryAuthenticationError,
    FoundryConfigurationError,
    FoundryError,
    FoundryServiceError,
)
from agentops.foundry.models import AgentInvocationResult, FoundryAgentVersion
from agentops.foundry.settings import FoundrySettings

__all__ = [
    "AgentInvocationResult",
    "FoundryAgentClient",
    "FoundryAgentNotFoundError",
    "FoundryAgentVersion",
    "FoundryAuthenticationError",
    "FoundryConfigurationError",
    "FoundryError",
    "FoundryServiceError",
    "FoundrySettings",
]
