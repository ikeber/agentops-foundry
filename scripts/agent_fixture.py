"""Create or delete a disposable Foundry agent for testing AgentOps.

This is a developer fixture, not part of AgentOps. AgentOps tests agents that already exist in
Foundry and never creates them. This script gives contributors an agent with two versions that
answer differently, so that version targeting (REQ-001) can be observed.

Run from the repository root:

    uv run --env-file .env python scripts/agent_fixture.py create --model <deployment-name>
    uv run --env-file .env python scripts/agent_fixture.py delete

The project comes from FOUNDRY_PROJECT_ENDPOINT and the agent name from FOUNDRY_AGENT_NAME.
Running ``create`` again on an existing agent adds two more versions. Run ``delete`` first for a
clean start.
"""

import argparse
import sys

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential

from agentops.foundry import FoundryConfigurationError, FoundrySettings

VERSION_INSTRUCTIONS = (
    "You are version one of a test agent. Begin every answer with 'V1:'.",
    "You are version two of a test agent. Begin every answer with 'V2:'.",
)


def create_agent(project: AIProjectClient, agent_name: str, model: str) -> None:
    """Create one agent version per entry in VERSION_INSTRUCTIONS."""
    for instructions in VERSION_INSTRUCTIONS:
        agent = project.agents.create_version(
            agent_name=agent_name,
            definition=PromptAgentDefinition(model=model, instructions=instructions),
        )
        print(f"Created {agent.name} version {agent.version}")


def delete_agent(project: AIProjectClient, agent_name: str) -> None:
    """Delete the agent and every version of it."""
    try:
        project.agents.delete(agent_name=agent_name)
    except ResourceNotFoundError:
        print(f"Agent {agent_name} does not exist, so there is nothing to delete.")
        return
    print(f"Deleted {agent_name} and all of its versions")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage the disposable Foundry test agent.")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Create the agent with two distinct versions.")
    create.add_argument(
        "--model",
        required=True,
        help="Model deployment name in the Foundry project, for example gpt-5-mini.",
    )
    commands.add_parser("delete", help="Delete the agent and all of its versions.")
    args = parser.parse_args(argv)

    try:
        settings = FoundrySettings.from_env()
    except FoundryConfigurationError as exc:
        print(f"FoundryConfigurationError: {exc}", file=sys.stderr)
        return 2

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=settings.project_endpoint, credential=credential) as project,
    ):
        if args.command == "create":
            create_agent(project, settings.agent_name, args.model)
        else:
            delete_agent(project, settings.agent_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
