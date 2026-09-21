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
