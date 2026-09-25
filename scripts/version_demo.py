"""Show that AgentOps pins each call to the requested Foundry agent version.

Run after ``agent_fixture.py create``, passing the version numbers it printed:

    uv run --env-file .env python scripts/version_demo.py 1 2

Each answer should start with the prefix its version was instructed to use, for example ``V1:``.
Failures print the AgentOps error type and message rather than a traceback.
"""

import argparse
import asyncio
import sys

from agentops.foundry import FoundryAgentClient, FoundryError, FoundrySettings

QUESTION = "In one short sentence, what are you for?"


async def run(versions: list[str]) -> None:
    settings = FoundrySettings.from_env()
    async with FoundryAgentClient.connect(settings) as foundry:
        latest = await foundry.resolve_version(settings.agent_name)
        print(f"Latest version of {settings.agent_name}: {latest.version}")
        for requested in versions:
            agent = await foundry.resolve_version(settings.agent_name, requested)
            result = await foundry.invoke(agent, QUESTION)
            print(f"[version {agent.version}] {result.output_text}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Invoke specific versions of the Foundry agent.")
    parser.add_argument("versions", nargs="+", help="Agent versions to invoke, for example 1 2.")
    args = parser.parse_args(argv)

    try:
        asyncio.run(run(args.versions))
    except FoundryError as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
