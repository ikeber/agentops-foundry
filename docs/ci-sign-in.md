# Non-interactive sign-in

This check proves that AgentOps can sign in to Microsoft Foundry as a service principal, with no person present. Continuous integration depends on that.

> **Interim page.** This check uses a short-lived client secret. The GitHub Actions quality gate for REQ-029 will use OpenID Connect federation instead, which stores no secret at all. That work's documentation will replace this page.
>
> The PowerShell commands come from the setup run on 2026-09-25, where this check was optional. The Bash commands have not been run against Azure.

Commands are shown for PowerShell, with Bash in collapsed sections.

## Before you start

- Complete Parts 1 to 3 of [Microsoft Foundry setup](foundry-setup.md), so that a project, a test agent and a `.env` file exist.
- Make sure the variables for the role ID and project ID are set. If you opened a new terminal, [restore the variables](foundry-setup.md#restore-the-variables-in-a-new-terminal) first.
- Skip this check if your tenant blocks app registrations.

The client secret lives only in the current terminal. The last step deletes the service principal, which also invalidates the secret.

## 1. Create a service principal with access to the project

```powershell
$sp = az ad sp create-for-rbac --name "agentops-sp-test" --output json | Out-String | ConvertFrom-Json
$SpObjectId = az ad sp show --id $sp.appId --query id -o tsv
az role assignment create --role $FoundryUser --assignee-object-id $SpObjectId --assignee-principal-type ServicePrincipal --scope $ProjectId

$env:AZURE_CLIENT_ID = $sp.appId
$env:AZURE_TENANT_ID = $sp.tenant
$env:AZURE_CLIENT_SECRET = $sp.password
$env:AZURE_TOKEN_CREDENTIALS = "EnvironmentCredential"
```

<details>
<summary>Bash</summary>

```bash
SP_JSON=$(az ad sp create-for-rbac --name "agentops-sp-test" --output json)
read -r AZURE_CLIENT_ID AZURE_TENANT_ID AZURE_CLIENT_SECRET < <(
  printf '%s' "$SP_JSON" | python3 -c 'import json, sys; d = json.load(sys.stdin); print(d["appId"], d["tenant"], d["password"])'
)
unset SP_JSON
SP_OBJECT_ID=$(az ad sp show --id "$AZURE_CLIENT_ID" --query id -o tsv)
az role assignment create --role "$FOUNDRY_USER" --assignee-object-id "$SP_OBJECT_ID" --assignee-principal-type ServicePrincipal --scope "$PROJECT_ID"

export AZURE_CLIENT_ID AZURE_TENANT_ID AZURE_CLIENT_SECRET
export AZURE_TOKEN_CREDENTIALS=EnvironmentCredential
```

</details>

Setting `AZURE_TOKEN_CREDENTIALS` makes AgentOps use only the service principal, so your own Azure CLI sign-in cannot mask a failure.

## 2. Invoke the agent as the service principal

Wait a few minutes for the role assignment to take effect, then run:

```sh
uv run --env-file .env python scripts/version_demo.py 2
```

The agent should answer as it does in [Part 4 of the setup guide](foundry-setup.md#part-4-verify-the-connection). If you see `FoundryAuthenticationError: Access was denied`, the role is not active yet. Wait and try again.

## 3. Clean up

```powershell
Remove-Item Env:AZURE_CLIENT_ID, Env:AZURE_TENANT_ID, Env:AZURE_CLIENT_SECRET, Env:AZURE_TOKEN_CREDENTIALS
az ad app delete --id $sp.appId
```

<details>
<summary>Bash</summary>

```bash
az ad app delete --id "$AZURE_CLIENT_ID"
unset AZURE_CLIENT_ID AZURE_TENANT_ID AZURE_CLIENT_SECRET AZURE_TOKEN_CREDENTIALS
```

</details>
