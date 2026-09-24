"""Connection settings for the Microsoft Foundry project and agent under test.

The settings hold identifiers only. They never hold secrets: Foundry supports Microsoft Entra ID
authentication exclusively, and credentials are resolved by ``azure-identity`` from the
developer's sign-in (``az login``) or from the standard ``AZURE_*`` environment variables used
by service principals and workload identity in CI.
"""

import os
import re
from collections.abc import Mapping
from typing import Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agentops.foundry.errors import FoundryConfigurationError

PROJECT_ENDPOINT_ENV = "FOUNDRY_PROJECT_ENDPOINT"
AGENT_NAME_ENV = "FOUNDRY_AGENT_NAME"

_ENV_BY_FIELD = {"project_endpoint": PROJECT_ENDPOINT_ENV, "agent_name": AGENT_NAME_ENV}
_PROJECT_PATH = re.compile(r"/api/projects/[^/]+")


class FoundrySettings(BaseModel):
    """Identifies the Foundry project and the agent that AgentOps tests."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    project_endpoint: str = Field(
        description=(
            "Foundry project endpoint, for example "
            "https://<resource>.services.ai.azure.com/api/projects/<project>."
        ),
    )
    agent_name: str = Field(min_length=1, description="Name of the Foundry agent under test.")

    @field_validator("project_endpoint")
    @classmethod
    def _validate_project_endpoint(cls, value: str) -> str:
        endpoint = value.rstrip("/")
        parts = urlsplit(endpoint)
        if (
            parts.scheme != "https"
            or not parts.netloc
            or parts.query
            or parts.fragment
            or not _PROJECT_PATH.fullmatch(parts.path)
        ):
            raise ValueError(
                "must be a Foundry project endpoint of the form "
                "https://<resource>.services.ai.azure.com/api/projects/<project>"
            )
        return endpoint

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        """Load settings from environment variables.

        Args:
            environ: Variables to read. Defaults to the process environment.

        Raises:
            FoundryConfigurationError: A required variable is missing or has an invalid value.
        """
        env = os.environ if environ is None else environ
        missing = [name for name in _ENV_BY_FIELD.values() if not env.get(name, "").strip()]
        if missing:
            raise FoundryConfigurationError(
                f"Missing required environment variable(s): {', '.join(missing)}. "
                "See .env.example for the expected values."
            )
        try:
            return cls(
                project_endpoint=env[PROJECT_ENDPOINT_ENV],
                agent_name=env[AGENT_NAME_ENV],
            )
        except ValidationError as exc:
            raise FoundryConfigurationError(_describe(exc)) from exc


def _describe(exc: ValidationError) -> str:
    problems = []
    for error in exc.errors():
        field = str(error["loc"][0]) if error["loc"] else "settings"
        problems.append(f"{_ENV_BY_FIELD.get(field, field)}: {error['msg']}")
    return "Invalid Foundry configuration. " + "; ".join(problems)
