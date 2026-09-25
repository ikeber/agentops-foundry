"""Live checks against a real Microsoft Foundry project.

These tests are deselected by default. Run them with:

    uv run --env-file .env pytest -m integration

They need FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_AGENT_NAME, an Entra ID sign-in such as
``az login``, and an existing agent in the project. They skip when the settings are missing.
"""

import pytest

from agentops.foundry import (
    FoundryAgentClient,
    FoundryAgentNotFoundError,
    FoundryConfigurationError,
    FoundrySettings,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def settings() -> FoundrySettings:
    try:
        return FoundrySettings.from_env()
    except FoundryConfigurationError as exc:
        pytest.skip(f"Microsoft Foundry is not configured: {exc}")


async def test_resolves_pins_and_invokes_the_configured_agent(settings: FoundrySettings) -> None:
    async with FoundryAgentClient.connect(settings) as foundry:
        latest = await foundry.resolve_version(settings.agent_name)
        pinned = await foundry.resolve_version(settings.agent_name, latest.version)
        result = await foundry.invoke(pinned, "Reply with a one-sentence greeting.")

    assert pinned == latest
    assert result.agent == pinned
    assert result.response_id
    assert result.output_text.strip()


async def test_unknown_version_is_reported_as_not_found(settings: FoundrySettings) -> None:
    async with FoundryAgentClient.connect(settings) as foundry:
        with pytest.raises(FoundryAgentNotFoundError):
            await foundry.resolve_version(settings.agent_name, "999999")
