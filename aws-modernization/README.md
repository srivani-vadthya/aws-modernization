# VModernize

VModernize is a local modernization control plane. It takes a legacy repository
through intake, discovery, scope selection, semantic analysis, requirements and
user stories, target architecture, Module Context Package creation, and an
approval-controlled modernization execution.

The product does **not** modify the cloned legacy repository. Provider work runs
in an isolated engagement workspace; generated output is stored under the API
data directory.

## Quick start

### Prerequisites

- Git
- Python 3.11–3.13
- Node.js 20 or later and npm
- PowerShell on Windows

For actual AWS Transform .NET modernization, also install:

- AWS Transform CLI (`atx`) and authenticate it with an authorized AWS profile
- .NET SDK 10 or later for the Transform worker (the generated target can still
  be .NET 8)

### 1. Clone and enter the repository

```powershell
git clone https://github.com/<your-org>/aws-modernization.git
cd aws-modernization
```

The following commands assume this directory contains `apps/api` and `apps/web`.

### 2. Configure the backend

```powershell
cd apps/api
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Open `.env` and configure only the integrations you intend to use. Never commit
this file. See [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md) for every variable.

### 3. Start the API

From `apps/api` with the virtual environment activated:

```powershell
python dev_server.py
```

The API starts at `http://127.0.0.1:8000`. This launcher watches only
`apps/api/app`, so package generation and execution artifacts do not restart the
backend on Windows.

### 4. Start the web application

Open a second PowerShell window:

```powershell
cd <repository-root>\apps\web
npm ci
npm run dev
```

Open the Vite URL shown in the terminal (normally `http://localhost:5173`).

## Normal workflow

1. Enter a legacy Git URL through the UI and create an engagement.
2. Review and approve the existing Discovery, Scope, Semantic IR, Requirements,
   and User Story stages.
3. Select and approve the target architecture.
4. Open **Code Modernization**, authorize the execution session, prepare the
   package/plan, and select **Start Modernization**.
5. Keep the API and web terminals running until the execution reaches a final
   status. Do not restart the API during provider execution.
6. Inspect generated artifacts in the Code Modernization screen or under the
   execution output directory described below.

## Generated output and safety

For an engagement ID `<engagement-id>` and execution ID `<execution-id>`, data is
stored locally at:

```text
apps/api/data/engagements/<engagement-id>/artifacts/modernization-executions/<execution-id>/
```

- `legacy-source/` — isolated working copy used by AWS Transform; never your
  original clone.
- `output/` — collected generated source and documentation after a provider task
  completes.
- `execution.json` — execution status, events, task history, and generated
  artifact metadata.

Do not treat staging content as final output until its task completes and the
execution records validation results.

## Verification

Backend tests:

```powershell
cd apps/api
.\.venv\Scripts\python.exe -m pytest tests -q
```

Frontend production build:

```powershell
cd apps/web
npm run build
```

## Documentation

- [Local installation, configuration, execution, and troubleshooting](docs/LOCAL_SETUP.md)
- [Modernization implementation guide](docs/MODERNIZATION_IMPLEMENTATION.md)
- [Module Context Package](docs/module-context-package.md)
- [Modernization Engine design history](docs/modernization-engine.md)
