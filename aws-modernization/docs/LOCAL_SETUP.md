# Local installation and provider configuration

This guide describes how to run VModernize on a new Windows machine without
committing credentials or modifying legacy source code.

## Prerequisites

| Component | Required for | Verify |
| --- | --- | --- |
| Git | Repository intake and cloning | `git --version` |
| Python 3.11–3.13 | FastAPI backend | `python --version` |
| Node.js 20+ and npm | React/Vite frontend | `node --version`, `npm --version` |
| .NET SDK 10+ | AWS Transform .NET worker only | `dotnet --list-sdks` |
| AWS Transform CLI (`atx`) | AWS Transform execution only | `atx --version` |

The modernization target may be .NET 8 even though the local Transform worker
requires SDK 10 or later.

## Backend installation

```powershell
cd <repository-root>\apps\api
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python dev_server.py
```

Expected health check: open `http://127.0.0.1:8000/api/meta`.

If PowerShell blocks virtual-environment activation, run this only for the active
PowerShell process and then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Frontend installation

```powershell
cd <repository-root>\apps\web
npm ci
npm run dev
```

Use `npm install` only when intentionally updating dependencies; use `npm ci` for
reproducible installation from `package-lock.json`.

## Environment configuration

Copy `apps/api/.env.example` to `apps/api/.env`. Values in `.env` are local-only
secrets/configuration and must not be pushed to Git.

### Core configuration

```dotenv
AWS_REGION=us-east-1
LLM_PROVIDER=bedrock
```

### Amazon Bedrock (for AI-backed generation)

Use **one** supported authentication path:

1. Bedrock API key:

```dotenv
BEDROCK_API_KEY=replace-with-your-api-key
BEDROCK_MODEL_ID=amazon.nova-pro-v1:0
BEDROCK_MODEL_FAST=amazon.nova-lite-v1:0
BEDROCK_MODEL_REASONING=amazon.nova-pro-v1:0
BEDROCK_MODEL_CODE=amazon.nova-pro-v1:0
```

2. Standard AWS SDK credentials/profile available to the backend process, for
example `AWS_PROFILE=your-profile`, or your normal AWS credential provider chain.

The selected AWS Region, model ID, and account must have Bedrock model access.
The application does not verify model access until an explicitly authorized
provider action occurs.

### AWS Transform (for supported .NET backend/API work)

Authenticate the AWS Transform CLI outside the application according to your
organization's AWS setup. Then configure the profile and optional metadata:

```dotenv
AWS_PROFILE=your-authorized-profile
# Optional when Transform uses a different profile:
# AWS_TRANSFORM_PROFILE=your-transform-profile

AWS_TRANSFORM_TENANT_ID=your-tenant-id
AWS_TRANSFORM_SERVICE_PROFILE_ARN=arn:aws:transform:<region>:<account>:profile/<profile-id>
AWS_TRANSFORM_PORTAL_URL=https://<tenant>.transform.<region>.on.aws/signin/

# Optional only if atx.cmd is not discoverable automatically:
# AWS_TRANSFORM_CLI_PATH=C:/path/to/atx.cmd
```

The current adapter invokes the installed `AWS/dotnet-modernization` definition
for approved .NET 8 backend/API tasks. It uses the selected module’s packaged
source closure and immutable golden-template snapshots. It does not use the outer
`BackendTemplate` or `FrontendTemplate` folders as authoritative templates.

### Browser execution authorization

Starting, viewing, or controlling modernization execution requires a short-lived,
server-managed browser session. Configure an operator token mapping locally:

```dotenv
EXECUTION_AUTH_TOKENS='{"replace-with-a-long-random-token":{"subject":"local-operator","permissions":["execution:read","execution:control"],"engagements":["*"]}}'
```

In the Code Modernization screen, paste the token once into the authorization
field. The browser exchanges it for an HttpOnly session cookie; it is not stored in
React source, browser local storage, or engagement artifacts. The current session
expires after a short period, so authorize again if execution polling returns 401.

Do not wrap a real token in extra quotes when pasting it into the browser field.

### Optional integrations

| Integration | Variables |
| --- | --- |
| Azure DevOps story export | `ADO_ORG`, `ADO_PROJECT`, `ADO_PAT` |
| GitHub publishing | `GITHUB_REPO`, `GITHUB_TOKEN` |
| Jira story export | `JIRA_BASE_URL`, `JIRA_PROJECT_KEY`, `JIRA_EMAIL`, `JIRA_API_TOKEN` |
| S3 source intake | `AWS_S3_INTAKE_BUCKET`, `AWS_S3_INTAKE_PREFIX`, optional `AWS_S3_SSE`, `AWS_S3_KMS_KEY_ID` |

Leave optional values blank when not using that integration.

## First run checklist

1. Start API and frontend in separate terminals.
2. Open the frontend URL.
3. Create an engagement from a Git repository URL or ZIP.
4. Work through and approve all upstream phases.
5. Select a target architecture and its applicable golden templates.
6. In Code Modernization, authorize execution, prepare, then start exactly one
   execution.
7. Keep the API process alive while AWS Transform/Bedrock is running.

The code-modernization panel shows persisted execution events. AWS Transform can
emit internal tool output; meaningful final output is available only after the
provider task reaches a completed state.

## Output locations

```text
apps/api/data/engagements/<engagement-id>/artifacts/
  module-context-packages/<package-id>/     immutable package + template snapshots
  modernization-plans/<plan-id>/            approved plan
  modernization-orchestrations/<id>/        task assignments
  modernization-executions/<execution-id>/
    legacy-source/                          isolated provider working copy
    output/                                 collected generated artifacts
    execution.json                          state, events, artifacts, failures
```

`legacy-source` is an isolated copied workspace. It can contain in-progress
provider changes. `output` contains only files collected after the corresponding
task completes. Neither location overwrites the original cloned legacy repository.

## Common issues

| Symptom | Cause and action |
| --- | --- |
| `401 Execution API authentication is required` | Enter a token matching `EXECUTION_AUTH_TOKENS` in the Code Modernization authorization control, then retry. Restart the backend after editing `.env`. |
| `422 Unprocessable Content` during prepare/start | Review the displayed readiness/approval requirements. Prepare a new package/plan after changing target/template selection. |
| `409 Conflict` during prepare | A preparation is already being created or a current record is being reused. Refresh and wait; do not repeatedly click Prepare. |
| Backend restarts while creating packages | Start with `python dev_server.py`, not a broad `uvicorn --reload` command. |
| Transform says .NET SDK is missing | Install .NET SDK 10+, restart PowerShell/API, verify with `dotnet --list-sdks`. |
| Transform cannot find `atx` | Install/authenticate AWS Transform CLI, or set `AWS_TRANSFORM_CLI_PATH` to `atx.cmd`. |
| Transform is still running but UI stops updating | Re-authorize the browser execution session. Do not restart the API: restart interrupts the local provider worker. |
| No final generated files in `output/` | Provider work is still in `legacy-source`, failed, or was interrupted. Inspect `execution.json` / UI terminal for the task status. |

## Before committing or pushing

```powershell
git status
git diff --check
cd apps/api; .\.venv\Scripts\python.exe -m pytest tests -q
cd ..\web; npm run build
```

Never commit `.env`, provider logs, generated engagement data, virtual environments,
or API keys/tokens. If a credential was pasted into a chat, terminal capture, or
committed file, rotate it in the relevant provider before sharing the repository.
