import pytest

from agentops.foundry import FoundryConfigurationError, FoundrySettings

ENDPOINT = "https://contoso.services.ai.azure.com/api/projects/policy"


def test_from_env_reads_project_endpoint_and_agent_name() -> None:
    settings = FoundrySettings.from_env(
        {"FOUNDRY_PROJECT_ENDPOINT": ENDPOINT, "FOUNDRY_AGENT_NAME": "policy-assistant"}
    )

    assert settings.project_endpoint == ENDPOINT
    assert settings.agent_name == "policy-assistant"


def test_from_env_normalises_whitespace_and_trailing_slash() -> None:
    settings = FoundrySettings.from_env(
        {"FOUNDRY_PROJECT_ENDPOINT": f" {ENDPOINT}/ ", "FOUNDRY_AGENT_NAME": " policy-assistant "}
    )

    assert settings.project_endpoint == ENDPOINT
    assert settings.agent_name == "policy-assistant"


def test_from_env_defaults_to_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("FOUNDRY_AGENT_NAME", "policy-assistant")

    assert FoundrySettings.from_env().agent_name == "policy-assistant"


def test_from_env_lists_every_missing_variable() -> None:
    with pytest.raises(FoundryConfigurationError) as excinfo:
        FoundrySettings.from_env({"FOUNDRY_AGENT_NAME": "   "})

    message = str(excinfo.value)
    assert "FOUNDRY_PROJECT_ENDPOINT" in message
    assert "FOUNDRY_AGENT_NAME" in message


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://contoso.services.ai.azure.com/api/projects/policy",
        "https://contoso.services.ai.azure.com",
        "https://contoso.openai.azure.com/openai/v1",
        "https://contoso.services.ai.azure.com/api/projects/",
        "https://contoso.services.ai.azure.com/api/projects/policy/agents",
        "https://contoso.services.ai.azure.com/api/projects/policy?api-version=v1",
        "contoso.services.ai.azure.com/api/projects/policy",
    ],
)
def test_from_env_rejects_values_that_are_not_project_endpoints(endpoint: str) -> None:
    with pytest.raises(FoundryConfigurationError, match="FOUNDRY_PROJECT_ENDPOINT"):
        FoundrySettings.from_env(
            {"FOUNDRY_PROJECT_ENDPOINT": endpoint, "FOUNDRY_AGENT_NAME": "policy-assistant"}
        )
