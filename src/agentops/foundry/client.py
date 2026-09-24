"""Adapter over the Microsoft Foundry SDK (``azure-ai-projects`` 2.x).

Foundry identifies agents by name and immutable version. This adapter resolves the version to
test, then invokes the agent through the project's OpenAI-compatible Responses API with an
``agent_reference`` pinned to that version. Pinning every call means a result can always be
attributed to the exact agent version that produced it (NFR-002).

All SDK exceptions are translated into :mod:`agentops.foundry.errors` types so that no Foundry
or OpenAI SDK types leak into AgentOps domain code.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Self

import openai
from azure.ai.projects.aio import AIProjectClient
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import (
    AzureError,
    ClientAuthenticationError,
    HttpResponseError,
    ResourceNotFoundError,
)
from azure.identity.aio import DefaultAzureCredential
from openai import AsyncOpenAI

from agentops.foundry.errors import (
    FoundryAgentNotFoundError,
    FoundryAuthenticationError,
    FoundryError,
    FoundryServiceError,
)
from agentops.foundry.models import AgentInvocationResult, FoundryAgentVersion
from agentops.foundry.settings import FoundrySettings

logger = logging.getLogger(__name__)

_FORBIDDEN = 403
_SIGN_IN_HINT = (
    "Sign in with `az login` for local development, or provide a service principal or "
    "workload identity through the standard AZURE_* environment variables."
)
_ACCESS_HINT = (
    "Check that the identity has the Foundry User role, formerly named Azure AI User, "
    "on the Foundry project."
)


class FoundryAgentClient:
    """Resolves and invokes agent versions in one Microsoft Foundry project.

    Create instances with :meth:`connect`, which owns the SDK clients' lifecycle.
    """

    def __init__(self, project_client: AIProjectClient, openai_client: AsyncOpenAI) -> None:
        self._project_client = project_client
        self._openai_client = openai_client

    @classmethod
    @asynccontextmanager
    async def connect(
        cls,
        settings: FoundrySettings,
        *,
        credential: AsyncTokenCredential | None = None,
    ) -> AsyncIterator[Self]:
        """Open a connection to the configured Foundry project.

        Args:
            settings: The project to connect to.
            credential: Entra ID credential to use. When omitted, a ``DefaultAzureCredential``
                is created and closed with the connection. A supplied credential is left open
                for its owner to close.
        """
        async with AsyncExitStack() as stack:
            active_credential: AsyncTokenCredential
            if credential is None:
                active_credential = await stack.enter_async_context(DefaultAzureCredential())
            else:
                active_credential = credential
            project_client = await stack.enter_async_context(
                AIProjectClient(endpoint=settings.project_endpoint, credential=active_credential)
            )
            openai_client = await stack.enter_async_context(project_client.get_openai_client())
            logger.debug("Connected to Foundry project %s", settings.project_endpoint)
            yield cls(project_client, openai_client)

    async def resolve_version(
        self, agent_name: str, version: str | None = None
    ) -> FoundryAgentVersion:
        """Look up an agent version, confirming that it exists.

        Args:
            agent_name: Name of the Foundry agent.
            version: Version to target. When omitted, the agent's latest version is resolved
                so that the concrete version can be recorded and pinned.

        Raises:
            FoundryAgentNotFoundError: The agent or version does not exist.
            FoundryAuthenticationError: Authentication or authorization failed.
            FoundryServiceError: Foundry could not complete the request.
        """
        subject = f"agent '{agent_name}'" + (f" version '{version}'" if version else "")
        try:
            if version is None:
                agent = await self._project_client.agents.get(agent_name=agent_name)
                details = agent.versions.latest
            else:
                details = await self._project_client.agents.get_version(
                    agent_name=agent_name, agent_version=version
                )
        except AzureError as exc:
            raise _translate_error(exc, f"resolving {subject}") from exc

        resolved = FoundryAgentVersion(
            agent_name=details.name,
            version=details.version,
            created_at=details.created_at,
            draft=bool(details.draft),
        )
        logger.info("Resolved Foundry agent '%s' to version '%s'", agent_name, resolved.version)
        return resolved

    async def invoke(self, agent: FoundryAgentVersion, prompt: str) -> AgentInvocationResult:
        """Send one input to a pinned agent version and return its response.

        Args:
            agent: The agent version to invoke, from :meth:`resolve_version`.
            prompt: The user input.

        Raises:
            ValueError: The prompt is empty.
            FoundryAgentNotFoundError: The agent version no longer exists.
            FoundryAuthenticationError: Authentication or authorization failed.
            FoundryServiceError: Foundry could not produce a response.
        """
        if not prompt.strip():
            raise ValueError("prompt must not be empty")

        subject = f"invoking agent '{agent.agent_name}' version '{agent.version}'"
        agent_reference = {
            "type": "agent_reference",
            "name": agent.agent_name,
            "version": agent.version,
        }
        try:
            response = await self._openai_client.responses.create(
                input=prompt,
                extra_body={"agent_reference": agent_reference},
            )
        except (AzureError, openai.APIError) as exc:
            raise _translate_error(exc, subject) from exc

        if response.status == "failed":
            detail = (
                f"{response.error.code}: {response.error.message}"
                if response.error
                else "no error detail returned"
            )
            raise FoundryServiceError(
                f"Foundry reported a failed response ({response.id}) while {subject}: {detail}"
            )

        logger.info(
            "Invoked Foundry agent '%s' version '%s' (response %s, status %s)",
            agent.agent_name,
            agent.version,
            response.id,
            response.status,
        )
        return AgentInvocationResult(
            agent=agent,
            response_id=response.id,
            status=response.status,
            output_text=response.output_text,
        )


def _translate_error(exc: AzureError | openai.APIError, subject: str) -> FoundryError:
    """Map an Azure or OpenAI SDK exception to an AgentOps adapter error."""
    if isinstance(exc, ClientAuthenticationError | openai.AuthenticationError):
        return FoundryAuthenticationError(
            f"Authentication to Microsoft Foundry failed while {subject}. {_SIGN_IN_HINT} "
            f"Detail: {exc}"
        )
    if isinstance(exc, openai.PermissionDeniedError) or (
        isinstance(exc, HttpResponseError) and exc.status_code == _FORBIDDEN
    ):
        return FoundryAuthenticationError(
            f"Access was denied while {subject}. {_ACCESS_HINT} Detail: {exc}"
        )
    if isinstance(exc, ResourceNotFoundError | openai.NotFoundError):
        return FoundryAgentNotFoundError(f"Not found while {subject}. Detail: {exc}")
    return FoundryServiceError(f"Microsoft Foundry request failed while {subject}. Detail: {exc}")
