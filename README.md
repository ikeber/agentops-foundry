# AgentOps for Microsoft Foundry

**Quality and policy engineering for Microsoft Foundry agents.**

AgentOps is an open-source quality and policy control plane for Microsoft Foundry agents.

It helps teams define expected agent behaviour, test each version against those expectations, detect regressions, and block releases that violate policy.

> **Define a Quality Contract. Test every version. Block releases that fail it.**

## V1 capabilities

* **Quality Contracts** — define grounding, evaluation, regression and safety requirements.
* **Source Precedence** — ensure authoritative sources take priority over stale or lower-trust content.
* **Evaluation** — combine deterministic checks with selected model-based evaluations.
* **Regression Testing** — compare baseline and candidate agent versions scenario by scenario.
* **Safety Verification** — verify that untrusted content cannot override grounding policy.
* **Quality Gates** — produce a clear `PASS` or `BLOCK` result for release decisions.

## How it works

```text
Microsoft Foundry Agent
→ Quality Contract
→ Grounding Policy
→ Test Dataset
→ Baseline vs Candidate
→ Evaluation
→ Regression
→ PASS / BLOCK
```

A core principle is:

> **Relevance is not the same as authority.**

AgentOps uses ordered grounding rules so authoritative information can take precedence over conflicting, outdated, or untrusted sources.

## Status

AgentOps is currently in early development, focused on delivering the first complete end-to-end quality gate for Microsoft Foundry agents.

## Development

### Prerequisites

* Python 3.12 or later and [uv](https://docs.astral.sh/uv/).
* The [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), for signing in locally.
* A Microsoft Foundry project that contains the agent to test. Your identity needs the **Foundry User** role on the project. This role was previously named Azure AI User.

### Set up

```bash
uv sync
```

For the full Azure setup, including creating a Foundry project, assigning roles, creating a test agent and verifying the connection, see [docs/foundry-setup.md](docs/foundry-setup.md).

### Connect to Microsoft Foundry

AgentOps authenticates to Foundry with Microsoft Entra ID, which is the only method the Foundry SDK supports. The repository never stores keys or secrets.

1. Sign in with `az login`. In CI, provide a service principal or workload identity through the standard `AZURE_*` environment variables that `azure-identity` reads.
2. Copy `.env.example` to `.env` and set `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_AGENT_NAME`. The `.env` file is git-ignored.

### Run checks

```bash
uv run pytest                                  # unit tests
uv run --env-file .env pytest -m integration   # live checks against your Foundry project
uv run mypy                                    # static type checks
uv run ruff check                              # lint
uv run ruff format --check                     # formatting
```

