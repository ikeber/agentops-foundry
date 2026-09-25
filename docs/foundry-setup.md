# Microsoft Foundry setup

This guide connects AgentOps to a Microsoft Foundry project and verifies the connection required by REQ-001. The Foundry integration spike under ADR-014 established this setup, and `requirements.md` and `architecture.md` record what it settled and what remains open.

> **Verification status.** Every PowerShell command here was run end to end on Windows 11 with Windows PowerShell on 2026-09-25. The Bash commands for macOS and Linux are direct translations that have not yet been run against Azure. If a Bash command behaves differently, please fix this guide.

Commands are shown for PowerShell. Where Bash differs, a collapsed **Bash** section follows the PowerShell block. A command with no Bash section is the same in both shells.

## Quick start: join an existing environment

Use this path if someone has already created the Foundry project. You need the [prerequisites](#prerequisites) and three things from whoever runs the environment:

- the project endpoint;
- the model deployment name, for example `gpt-5-mini`;
- the Foundry User role on the project for your account, assigned as shown in [1.5](#15-grant-access).

Run these from the repository root:

```sh
uv sync
az login
cp .env.example .env
```

Edit `.env`. Set `FOUNDRY_PROJECT_ENDPOINT` to the endpoint. Set `FOUNDRY_AGENT_NAME` to a test agent name of your own, such as `agentops-<your-name>-test`, so your fixture stays separate from your teammates' in the shared project. Then create your test agent and run the live tests:

```sh
uv run --env-file .env python scripts/agent_fixture.py create --model gpt-5-mini
uv run --env-file .env pytest -m integration -v
```

Both live tests should pass. When you finish, delete your test agent:

```sh
uv run --env-file .env python scripts/agent_fixture.py delete
```

To set up a new environment from scratch, follow the rest of this guide.

## How the full setup is organised

| Part | What it creates | How often |
|---|---|---|
| [1. Development environment](#part-1-development-environment) | Resource group, Foundry resource and project, model deployment, role assignments | Once per developer or team |
| [2. Local configuration](#part-2-local-configuration) | A `.env` file with the project endpoint and agent name | Once per clone |
| [3. Test fixtures](#part-3-test-fixtures) | A disposable agent with two versions | Per feature or test run, deleted afterwards |
| [4. Verify the connection](#part-4-verify-the-connection) | Nothing | After setup, and whenever you need to check the connection |

Keep the development environment for the life of the project. Recreating it for each feature repeats quota checks and role propagation, and leaves soft-deleted resource names behind. To isolate work, give each feature or test run its own agent name instead.

## Prerequisites

- An Azure subscription where you can create resources and assign roles. The **Owner** role on the subscription or on a resource group covers both. The quick start needs only the Foundry User role on the project.
- Python 3.12 or later.
- [uv](https://docs.astral.sh/uv/getting-started/installation/). Check it with `uv --version`.
- The [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), version 2.80.0 or later. Earlier versions lack the `az cognitiveservices account project` commands.
  - Windows: `winget install --exact --id Microsoft.AzureCLI`
  - macOS: `brew install azure-cli`
  - Linux: follow the Azure CLI instructions for your distribution.
- The project dependencies. Run `uv sync` from the repository root.

On Windows, restart VS Code completely after installing a tool so that its terminal picks up the new `PATH`.

Run every command from the repository root, in one terminal. Later steps reuse variables that earlier steps set. If you open a new terminal, first [restore the variables](#restore-the-variables-in-a-new-terminal).

## Part 1: Development environment

### 1.1 Sign in

```sh
az version
az login
az account set --subscription "<subscription name or id>"
az provider register --namespace Microsoft.CognitiveServices
```

If your account belongs to several Microsoft Entra tenants, sign in with `az login --tenant "<tenant-id>"` instead.

### 1.2 Choose names

The Foundry resource name becomes a public hostname, `<name>.services.ai.azure.com`, so it must be globally unique. The random suffix takes care of that. Write down the printed name, because you need it to restore your variables later.

The role ID identifies the **Foundry User** role. Microsoft recently renamed the Foundry roles, and Foundry User was previously called Azure AI User. The ID did not change, so the commands use it instead of the name.

```powershell
$Location      = "eastus"
$ResourceGroup = "rg-agentops-dev"
$Resource      = "agentops-dev-$(Get-Random -Maximum 99999)"
$Project       = "agentops-dev"
$Model         = "gpt-5-mini"
$AgentName     = "agentops-test-agent"
$FoundryUser   = "53ca6127-db72-4b80-b1b0-d745d6d5456d"   # Foundry User role
$Resource
```

<details>
<summary>Bash</summary>

```bash
LOCATION="eastus"
RESOURCE_GROUP="rg-agentops-dev"
RESOURCE="agentops-dev-$RANDOM"
PROJECT="agentops-dev"
MODEL="gpt-5-mini"
AGENT_NAME="agentops-test-agent"
FOUNDRY_USER="53ca6127-db72-4b80-b1b0-d745d6d5456d"   # Foundry User role
echo "$RESOURCE"
```

</details>

### 1.3 Create the resource group, Foundry resource and project

```powershell
az group create --name $ResourceGroup --location $Location

az cognitiveservices account create `
  --name $Resource `
  --resource-group $ResourceGroup `
  --kind AIServices `
  --sku S0 `
  --location $Location `
  --custom-domain $Resource `
  --assign-identity `
  --allow-project-management true

az cognitiveservices account project create `
  --name $Resource `
  --resource-group $ResourceGroup `
  --project-name $Project `
  --location $Location

az cognitiveservices account project show --name $Resource --resource-group $ResourceGroup --project-name $Project --query properties.provisioningState -o tsv
```

<details>
<summary>Bash</summary>

```bash
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

az cognitiveservices account create \
  --name "$RESOURCE" \
  --resource-group "$RESOURCE_GROUP" \
  --kind AIServices \
  --sku S0 \
  --location "$LOCATION" \
  --custom-domain "$RESOURCE" \
  --assign-identity \
  --allow-project-management true

az cognitiveservices account project create \
  --name "$RESOURCE" \
  --resource-group "$RESOURCE_GROUP" \
  --project-name "$PROJECT" \
  --location "$LOCATION"

az cognitiveservices account project show --name "$RESOURCE" --resource-group "$RESOURCE_GROUP" --project-name "$PROJECT" --query properties.provisioningState -o tsv
```

</details>

The last command prints `Succeeded`. Project management requires the resource's managed identity, which `--assign-identity` creates. You cannot turn `--allow-project-management` on after the resource exists.

### 1.4 Deploy a model

The test agent needs a model to answer questions. AgentOps does not depend on a particular model, so any chat model your region offers works. First list the versions available in your region.

```powershell
$models = az cognitiveservices model list --location $Location --output json | Out-String | ConvertFrom-Json
$models |
  Where-Object { $_.model.name -eq $Model } |
  ForEach-Object { [pscustomobject]@{ Version = $_.model.version; Skus = ($_.model.skus.name -join ', ') } } |
  Sort-Object Version -Unique |
  Format-Table
```

<details>
<summary>Bash</summary>

```bash
az cognitiveservices model list --location "$LOCATION" \
  --query "[?model.name=='$MODEL'].{version:model.version,skus:join(', ',model.skus[].name)}" \
  --output table
```

</details>

The two shells differ here because, on Windows, `az` is a batch file. Its arguments pass through `cmd.exe`, which misreads the braces, pipes and quotes in a complex `--query` and fails with `} was unexpected at this time`. PowerShell therefore filters the JSON output itself.

Choose a version whose SKU list includes `GlobalStandard`, then deploy it. In September 2026, Microsoft's quickstart used version `2025-08-07`. Capacity is in thousands of tokens per minute, and 10 is plenty for testing.

```powershell
$ModelVersion = "2025-08-07"
az cognitiveservices account deployment create `
  --name $Resource `
  --resource-group $ResourceGroup `
  --deployment-name $Model `
  --model-name $Model `
  --model-version $ModelVersion `
  --model-format OpenAI `
  --sku-capacity 10 `
  --sku-name GlobalStandard
```

<details>
<summary>Bash</summary>

```bash
MODEL_VERSION="2025-08-07"
az cognitiveservices account deployment create \
  --name "$RESOURCE" \
  --resource-group "$RESOURCE_GROUP" \
  --deployment-name "$MODEL" \
  --model-name "$MODEL" \
  --model-version "$MODEL_VERSION" \
  --model-format OpenAI \
  --sku-capacity 10 \
  --sku-name GlobalStandard
```

</details>

### 1.5 Grant access

Creating Foundry resources with the Azure CLI or SDK does not grant anyone data access. The Owner and Contributor roles manage resources but cannot read or call agents. This step gives you the Foundry User role on the project. It also gives the project's managed identity the same role on the resource, which is Microsoft's documented minimum setup.

```powershell
$ProjectId  = az cognitiveservices account project show --name $Resource --resource-group $ResourceGroup --project-name $Project --query id -o tsv
$ResourceId = az cognitiveservices account show --name $Resource --resource-group $ResourceGroup --query id -o tsv
$MyObjectId = az ad signed-in-user show --query id -o tsv

az role assignment create --role $FoundryUser --assignee-object-id $MyObjectId --assignee-principal-type User --scope $ProjectId

$ProjectIdentity = az cognitiveservices account project show --name $Resource --resource-group $ResourceGroup --project-name $Project --query identity.principalId -o tsv
if ($ProjectIdentity) {
  az role assignment create --role $FoundryUser --assignee-object-id $ProjectIdentity --assignee-principal-type ServicePrincipal --scope $ResourceId
} else { "Project has no managed identity; skipping that assignment." }
```

<details>
<summary>Bash</summary>

```bash
PROJECT_ID=$(az cognitiveservices account project show --name "$RESOURCE" --resource-group "$RESOURCE_GROUP" --project-name "$PROJECT" --query id -o tsv)
RESOURCE_ID=$(az cognitiveservices account show --name "$RESOURCE" --resource-group "$RESOURCE_GROUP" --query id -o tsv)
MY_OBJECT_ID=$(az ad signed-in-user show --query id -o tsv)

az role assignment create --role "$FOUNDRY_USER" --assignee-object-id "$MY_OBJECT_ID" --assignee-principal-type User --scope "$PROJECT_ID"

PROJECT_IDENTITY=$(az cognitiveservices account project show --name "$RESOURCE" --resource-group "$RESOURCE_GROUP" --project-name "$PROJECT" --query identity.principalId -o tsv)
if [ -n "$PROJECT_IDENTITY" ]; then
  az role assignment create --role "$FOUNDRY_USER" --assignee-object-id "$PROJECT_IDENTITY" --assignee-principal-type ServicePrincipal --scope "$RESOURCE_ID"
else
  echo "Project has no managed identity; skipping that assignment."
fi
```

</details>

Role assignments can take several minutes to take effect.

To give a teammate access, assign the same role to their account at the project scope. Use the project ID stored in `$ProjectId` in PowerShell or `$PROJECT_ID` in Bash.

```sh
az role assignment create --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --assignee "colleague@example.com" --assignee-principal-type User --scope "<project-id>"
```

## Part 2: Local configuration

AgentOps reads two settings, the project endpoint and the name of the agent under test. They are identifiers, not secrets. Credentials come from your Entra ID sign-in, so nothing secret is written to disk. The `.env` file is git-ignored, and `.env.example` documents its format.

```powershell
$Endpoint = (az cognitiveservices account project show --name $Resource --resource-group $ResourceGroup --project-name $Project --output json | Out-String | ConvertFrom-Json).properties.endpoints.'AI Foundry API'
$Endpoint

@"
FOUNDRY_PROJECT_ENDPOINT=$Endpoint
FOUNDRY_AGENT_NAME=$AgentName
"@ | Set-Content -Encoding ascii .env

Get-Content .env
```

<details>
<summary>Bash</summary>

```bash
ENDPOINT=$(az cognitiveservices account project show --name "$RESOURCE" --resource-group "$RESOURCE_GROUP" --project-name "$PROJECT" --query 'properties.endpoints."AI Foundry API"' -o tsv)
echo "$ENDPOINT"

printf 'FOUNDRY_PROJECT_ENDPOINT=%s\nFOUNDRY_AGENT_NAME=%s\n' "$ENDPOINT" "$AGENT_NAME" > .env

cat .env
```

</details>

The endpoint has the form `https://<resource>.services.ai.azure.com/api/projects/<project>`. If it comes back empty, build it from the resource and project names in that form.

In Windows PowerShell, keep `-Encoding ascii`. Its `utf8` option adds a byte-order mark, and uv then silently ignores the file.

## Part 3: Test fixtures

AgentOps tests agents that already exist in Foundry and never creates them. To test against something predictable, create a disposable agent with two versions that answer differently. Replace `gpt-5-mini` with your deployment name if it differs.

```sh
uv run --env-file .env python scripts/agent_fixture.py create --model gpt-5-mini
```

It prints the versions it creates:

```text
Created agentops-test-agent version 1
Created agentops-test-agent version 2
```

Version 1 is told to begin every answer with `V1:`, and version 2 with `V2:`. Running `create` again on the same agent adds two more versions, so delete the agent first if you want a clean start.

For a separate fixture per feature or test run, change `FOUNDRY_AGENT_NAME` in `.env` to a name such as `agentops-req019-test` before running `create`. Agent names must start and end with a letter or digit, may contain hyphens, and can be up to 63 characters long.

Delete a fixture when you finish with it. This removes the agent and all of its versions:

```sh
uv run --env-file .env python scripts/agent_fixture.py delete
```

### About the scripts folder

`scripts/` holds developer and test-fixture tooling that acts on a Foundry project. It is not part of the AgentOps package, and nothing in `src/` imports it. The scripts are linted and type-checked with the rest of the repository. Whether demo provisioning for REQ-031 will also live here has not been decided.

| Script | Purpose |
|---|---|
| `scripts/agent_fixture.py` | Creates or deletes the disposable test agent |
| `scripts/version_demo.py` | Invokes chosen agent versions through the AgentOps adapter and prints each answer |

## Part 4: Verify the connection

These checks cover the three REQ-001 acceptance criteria: configured credentials, invoking the agent, and targeting a specific version.

**Unit tests.** They confirm the local build and need no Azure access. The live tests are deselected by default.

```sh
uv run pytest
```

**Live tests.** Both should pass.

```sh
uv run --env-file .env pytest -m integration -v
```

The first test resolves the agent's latest version, pins it explicitly, invokes it and expects a non-empty answer. The second requests a version that does not exist and expects a not-found error.

**Version targeting.** Pass the version numbers that the fixture script printed:

```sh
uv run --env-file .env python scripts/version_demo.py 1 2
```

Expected output, although the model's wording varies:

```text
Latest version of agentops-test-agent: 2
[version 1] V1: ...
[version 2] V2: ...
```

The `V1:` and `V2:` prefixes show that each call reached the version it was pinned to.

**Missing configuration.** Run without the `.env` file:

```sh
uv run python scripts/version_demo.py 1
```

This prints `FoundryConfigurationError` and names both missing variables.

**Signed out.** Restricting the credential to the Azure CLI stops a sign-in from VS Code or Azure PowerShell from quietly taking over.

```powershell
az logout
$env:AZURE_TOKEN_CREDENTIALS = "AzureCliCredential"
uv run --env-file .env python scripts/version_demo.py 1
Remove-Item Env:AZURE_TOKEN_CREDENTIALS
az login
```

<details>
<summary>Bash</summary>

```bash
az logout
AZURE_TOKEN_CREDENTIALS=AzureCliCredential uv run --env-file .env python scripts/version_demo.py 1
az login
```

</details>

This prints `FoundryAuthenticationError` with a hint to run `az login`. After signing in again, select the same subscription.

To check that AgentOps can also sign in as a service principal, with no person present, see [Non-interactive sign-in](ci-sign-in.md).

## Restore the variables in a new terminal

Shell variables disappear when you close the terminal or restart VS Code. These commands set them again and look up the Foundry resource name. They assume the resource group contains one Foundry resource.

```powershell
$Location      = "eastus"
$ResourceGroup = "rg-agentops-dev"
$Project       = "agentops-dev"
$Model         = "gpt-5-mini"
$AgentName     = "agentops-test-agent"
$FoundryUser   = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
$Resource  = (az cognitiveservices account list --resource-group $ResourceGroup --output json | Out-String | ConvertFrom-Json)[0].name
$ProjectId = az cognitiveservices account project show --name $Resource --resource-group $ResourceGroup --project-name $Project --query id -o tsv
$Resource
```

<details>
<summary>Bash</summary>

```bash
LOCATION="eastus"
RESOURCE_GROUP="rg-agentops-dev"
PROJECT="agentops-dev"
MODEL="gpt-5-mini"
AGENT_NAME="agentops-test-agent"
FOUNDRY_USER="53ca6127-db72-4b80-b1b0-d745d6d5456d"
RESOURCE=$(az cognitiveservices account list --resource-group "$RESOURCE_GROUP" --query '[0].name' -o tsv)
PROJECT_ID=$(az cognitiveservices account project show --name "$RESOURCE" --resource-group "$RESOURCE_GROUP" --project-name "$PROJECT" --query id -o tsv)
echo "$RESOURCE"
```

</details>

## Clean up

- **Test fixtures.** Delete each fixture agent when you finish with it, as shown in [Part 3](#part-3-test-fixtures).
- **Foundry only.** To remove the Foundry resource and everything in it but keep the resource group, run `az cognitiveservices account delete --name "<resource>" --resource-group "<group>"`.
- **Everything.** To remove the whole development environment, delete the resource group:

  ```sh
  az group delete --name rg-agentops-dev --yes --no-wait
  ```

Azure keeps a deleted Foundry resource in a soft-deleted state for a period and reserves its name meanwhile. To reuse the exact name sooner, purge it:

```sh
az cognitiveservices account purge --location "<location>" --resource-group "<group>" --name "<resource>"
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `'project' is misspelled or not recognized`, or unrecognized arguments | Azure CLI older than 2.80.0 | Run `az upgrade` |
| `CustomDomainInUse` | The resource name is taken | Choose a new name in [1.2](#12-choose-names) |
| `DeploymentModelNotSupported` | The model version or SKU is not offered in the region | Pick a listed version, or another region |
| Quota error when deploying | No quota for the model in the region | Lower `--sku-capacity`, or request more quota |
| `} was unexpected at this time` | Windows `cmd.exe` misreading a complex `--query` | Filter JSON in PowerShell, as in [1.4](#14-deploy-a-model) |
| `uv` is not recognized | uv's folder is not on `PATH`, or the terminal predates the change | Add uv to `PATH`, then restart VS Code completely |
| `No module named uv` | `python -m uv` ran inside the project's `.venv`, which does not contain uv | Call `uv` directly |
| `No environment file found at: .env` | The command ran outside the repository root, or `.env` was never created | Change to the repository root, or complete [Part 2](#part-2-local-configuration) |
| `FoundryConfigurationError` although `.env` exists | `--env-file .env` was left out, or the file has a byte-order mark | Add the option, or recreate the file with the Part 2 commands |
| `FoundryAuthenticationError: Authentication ... failed` | Not signed in, or signed in to the wrong tenant | Run `az login`, adding `--tenant` if needed |
| `FoundryAuthenticationError: Access was denied` | The Foundry User role is missing or not yet active | Wait a few minutes, then check [1.5](#15-grant-access) |
| `FoundryAgentNotFoundError` | The agent name in `.env` does not match, or the version does not exist | Run the fixture script, and compare names and versions |
| Variables are empty | The terminal was closed or VS Code restarted | [Restore the variables](#restore-the-variables-in-a-new-terminal) |

## References

- [Create a Foundry project](https://learn.microsoft.com/azure/foundry/how-to/create-projects)
- [Quickstart: set up Microsoft Foundry resources](https://learn.microsoft.com/azure/foundry/tutorials/quickstart-create-foundry-resources)
- [Deploy models with the Azure CLI](https://learn.microsoft.com/azure/foundry/foundry-models/how-to/create-model-deployments)
- [Role-based access control for Microsoft Foundry](https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry)
- [Runtime components in Foundry Agent Service](https://learn.microsoft.com/azure/foundry/agents/concepts/runtime-components)
