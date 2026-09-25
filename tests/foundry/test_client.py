from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self, cast

import httpx2
import openai
import pytest
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    AgentDetails,
    AgentObjectType,
    AgentObjectVersions,
    AgentVersionDetails,
    PromptAgentDefinition,
)
from azure.core.credentials import AccessToken
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ResourceNotFoundError,
    ServiceRequestError,
)
from azure.identity import CredentialUnavailableError
from openai import AsyncOpenAI
from openai.types.responses import Response

from agentops.foundry import (
    FoundryAgentClient,
    FoundryAgentNotFoundError,
    FoundryAgentVersion,
    FoundryAuthenticationError,
    FoundryError,
    FoundryServiceError,
    FoundrySettings,
)
from agentops.foundry import client as client_module

AGENT_NAME = "policy-assistant"
CREATED_AT = datetime(2026, 9, 1, tzinfo=UTC)
SETTINGS = FoundrySettings(
    project_endpoint="https://contoso.services.ai.azure.com/api/projects/policy",
    agent_name=AGENT_NAME,
)


def make_version(version: str, *, draft: bool | None = None) -> AgentVersionDetails:
    return AgentVersionDetails(
        object=AgentObjectType.AGENT_VERSION,
        id=f"{AGENT_NAME}:{version}",
        name=AGENT_NAME,
        version=version,
        created_at=CREATED_AT,
        definition=PromptAgentDefinition(model="gpt-5"),
        metadata={},
        draft=draft,
    )


def make_response(*, status: str = "completed", error: dict[str, str] | None = None) -> Response:
    return Response.model_validate(
        {
            "id": "resp_123",
            "object": "response",
            "created_at": 1_788_000_000,
            "model": "gpt-5",
            "status": status,
            "output": [
                {
                    "type": "message",
                    "id": "msg_1",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "Ready.", "annotations": []}],
                }
            ],
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "error": error,
            "incomplete_details": None,
            "instructions": None,
            "metadata": {},
            "temperature": None,
            "top_p": None,
        }
    )


def openai_status_error(error_type: type[openai.APIStatusError], status: int) -> Exception:
    request = httpx2.Request("POST", "https://contoso.services.ai.azure.com/openai/v1/responses")
    response = httpx2.Response(status, request=request)
    return error_type("request failed", response=response, body=None)


def forbidden() -> HttpResponseError:
    error = HttpResponseError(message="Principal does not have access")
    error.status_code = 403
    return error


class FakeAgents:
    def __init__(self, *versions: AgentVersionDetails, error: Exception | None = None) -> None:
        self._versions = {details.version: details for details in versions}
        self._error = error
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def get(self, *, agent_name: str) -> AgentDetails:
        self.calls.append(("get", {"agent_name": agent_name}))
        if self._error:
            raise self._error
        latest = max(self._versions.values(), key=lambda details: int(details.version))
        return AgentDetails(
            object=AgentObjectType.AGENT,
            id=agent_name,
            name=agent_name,
            versions=AgentObjectVersions(latest=latest),
        )

    async def get_version(self, *, agent_name: str, agent_version: str) -> AgentVersionDetails:
        self.calls.append(
            ("get_version", {"agent_name": agent_name, "agent_version": agent_version})
        )
        if self._error:
            raise self._error
        if agent_version not in self._versions:
            raise ResourceNotFoundError(f"Agent version {agent_version} not found")
        return self._versions[agent_version]


class FakeResponses:
    def __init__(self, response: Response | None = None, error: Exception | None = None) -> None:
        self._response = response or make_response()
        self._error = error
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Response:
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._response


class FakeProjectClient:
    def __init__(self, agents: FakeAgents) -> None:
        self.agents = agents


class FakeOpenAIClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses


class FakeCredential:
    """An async Entra ID credential that records whether it was closed and never issues tokens."""

    def __init__(self) -> None:
        self.closed = False

    async def get_token(self, *scopes: str, **kwargs: Any) -> AccessToken:
        raise AssertionError("unit tests must not request tokens")

    async def close(self) -> None:
        self.closed = True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self.close()


def make_client(
    agents: FakeAgents | None = None, responses: FakeResponses | None = None
) -> FoundryAgentClient:
    project = FakeProjectClient(agents or FakeAgents(make_version("1"), make_version("2")))
    openai_client = FakeOpenAIClient(responses or FakeResponses())
    return FoundryAgentClient(cast(AIProjectClient, project), cast(AsyncOpenAI, openai_client))


PINNED = FoundryAgentVersion(agent_name=AGENT_NAME, version="2", created_at=CREATED_AT)


class TestResolveVersion:
    async def test_without_version_resolves_latest_to_a_concrete_version(self) -> None:
        agents = FakeAgents(make_version("1"), make_version("2"))

        resolved = await make_client(agents).resolve_version(AGENT_NAME)

        assert resolved == FoundryAgentVersion(
            agent_name=AGENT_NAME, version="2", created_at=CREATED_AT, draft=False
        )
        assert agents.calls == [("get", {"agent_name": AGENT_NAME})]

    async def test_with_version_targets_that_exact_version(self) -> None:
        agents = FakeAgents(make_version("1"), make_version("2", draft=True))

        resolved = await make_client(agents).resolve_version(AGENT_NAME, "2")

        assert resolved.version == "2"
        assert resolved.draft is True
        assert agents.calls == [("get_version", {"agent_name": AGENT_NAME, "agent_version": "2"})]

    async def test_unknown_version_raises_not_found(self) -> None:
        with pytest.raises(FoundryAgentNotFoundError, match="version '9'"):
            await make_client().resolve_version(AGENT_NAME, "9")

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (ResourceNotFoundError("Agent not found"), FoundryAgentNotFoundError),
            (ClientAuthenticationError("Token rejected"), FoundryAuthenticationError),
            (CredentialUnavailableError("No credential"), FoundryAuthenticationError),
            (forbidden(), FoundryAuthenticationError),
            (HttpResponseError(message="Internal server error"), FoundryServiceError),
            (ServiceRequestError("Connection refused"), FoundryServiceError),
        ],
    )
    async def test_sdk_errors_are_translated(
        self, error: Exception, expected: type[FoundryError]
    ) -> None:
        client = make_client(FakeAgents(error=error))

        with pytest.raises(expected) as excinfo:
            await client.resolve_version(AGENT_NAME)

        assert excinfo.value.__cause__ is error


class TestInvoke:
    async def test_pins_the_agent_reference_to_the_resolved_version(self) -> None:
        responses = FakeResponses()

        await make_client(responses=responses).invoke(PINNED, "What is the leave policy?")

        assert responses.calls == [
            {
                "input": "What is the leave policy?",
                "extra_body": {
                    "agent_reference": {
                        "type": "agent_reference",
                        "name": AGENT_NAME,
                        "version": "2",
                    }
                },
            }
        ]

    async def test_returns_the_response_attributed_to_the_pinned_version(self) -> None:
        result = await make_client().invoke(PINNED, "What is the leave policy?")

        assert result.agent == PINNED
        assert result.response_id == "resp_123"
        assert result.status == "completed"
        assert result.output_text == "Ready."

    @pytest.mark.parametrize("prompt", ["", "   "])
    async def test_rejects_an_empty_prompt(self, prompt: str) -> None:
        responses = FakeResponses()

        with pytest.raises(ValueError, match="prompt"):
            await make_client(responses=responses).invoke(PINNED, prompt)

        assert responses.calls == []

    async def test_failed_response_raises_service_error_with_detail(self) -> None:
        response = make_response(
            status="failed", error={"code": "server_error", "message": "Model unavailable"}
        )

        with pytest.raises(FoundryServiceError, match="server_error: Model unavailable"):
            await make_client(responses=FakeResponses(response)).invoke(PINNED, "Hello")

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (openai_status_error(openai.NotFoundError, 404), FoundryAgentNotFoundError),
            (openai_status_error(openai.AuthenticationError, 401), FoundryAuthenticationError),
            (openai_status_error(openai.PermissionDeniedError, 403), FoundryAuthenticationError),
            (openai_status_error(openai.InternalServerError, 500), FoundryServiceError),
            (
                openai.APIConnectionError(
                    request=httpx2.Request("POST", "https://contoso.services.ai.azure.com")
                ),
                FoundryServiceError,
            ),
            (CredentialUnavailableError("No credential"), FoundryAuthenticationError),
        ],
    )
    async def test_sdk_errors_are_translated(
        self, error: Exception, expected: type[FoundryError]
    ) -> None:
        client = make_client(responses=FakeResponses(error=error))

        with pytest.raises(expected) as excinfo:
            await client.invoke(PINNED, "Hello")

        assert excinfo.value.__cause__ is error


class TestConnect:
    async def test_uses_the_project_openai_endpoint(self) -> None:
        credential = FakeCredential()

        async with FoundryAgentClient.connect(SETTINGS, credential=credential) as foundry:
            base_url = str(foundry._openai_client.base_url)

        assert base_url == f"{SETTINGS.project_endpoint}/openai/v1/"

    async def test_leaves_a_caller_supplied_credential_open(self) -> None:
        credential = FakeCredential()

        async with FoundryAgentClient.connect(SETTINGS, credential=credential):
            pass

        assert credential.closed is False

    async def test_creates_and_closes_a_default_credential_when_none_is_supplied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        created: list[FakeCredential] = []

        def fake_default_credential() -> FakeCredential:
            created.append(FakeCredential())
            return created[-1]

        monkeypatch.setattr(client_module, "DefaultAzureCredential", fake_default_credential)

        async with FoundryAgentClient.connect(SETTINGS):
            assert len(created) == 1
            assert created[0].closed is False

        assert created[0].closed is True
