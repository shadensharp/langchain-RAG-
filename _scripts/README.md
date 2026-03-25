# Script Entry Points

These scripts are intended to be the narrow permission boundary for Codex.

## Backend

- `run_backend.ps1`: starts the FastAPI backend with the repo `.venv`
- `powershell -File _scripts/run_backend.ps1`
- `powershell -File _scripts/run_backend.ps1 -Reload`
- `run_ingest.ps1`: runs ingest and defaults the record manager to local SQLite
- `powershell -File _scripts/run_ingest.ps1`
- `run_ingest.ps1 -UseConfiguredRecordManager`: opts back into the configured RECORD_MANAGER_DB_URL
- `powershell -File _scripts/run_ingest.ps1 -UseConfiguredRecordManager`
- `run_ingest.ps1 -UseLocalRecordManager`: uses an explicit local SQLite record-manager override
- `powershell -File _scripts/run_ingest.ps1 -UseLocalRecordManager`

## Frontend

- `build_frontend.ps1`: runs the local `next build` CLI directly
- `powershell -File _scripts/build_frontend.ps1`
- `run_frontend_dev.ps1`: runs the local `next dev` CLI directly
- `powershell -File _scripts/run_frontend_dev.ps1`

The frontend scripts intentionally bypass global `yarn` to avoid Windows shim and user-profile path issues.

## Dry run

Each script supports `-DryRun` to print the exact command without executing it.
