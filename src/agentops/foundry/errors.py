"""Errors raised by the Microsoft Foundry adapter.

Every error here describes an execution or infrastructure problem (configuration, identity,
missing resources, service failures). None of them is evidence that an agent violated its
Quality Contract, so callers can report them separately from quality failures (NFR-013).
"""


class FoundryError(Exception):
    """Base class for all Microsoft Foundry adapter errors."""


class FoundryConfigurationError(FoundryError):
    """The Foundry connection settings are missing or invalid."""


class FoundryAuthenticationError(FoundryError):
    """AgentOps could not authenticate to Foundry, or its identity lacks access."""


class FoundryAgentNotFoundError(FoundryError):
    """The requested agent, or the requested version of it, does not exist in the project."""


class FoundryServiceError(FoundryError):
    """Foundry could not complete a request because of a service, network, or runtime failure."""
