# Change Data Management Service (CDMS)

CDMS is a backend project focused on capturing new products and changes to product information from an inventory service.

Its purpose is to maintain the latest accepted product state and a history of meaningful changes, while preventing duplicate processing and stale updates from overwriting newer data.

The service is designed to receive product snapshots through webhook callbacks, scheduled polling, and Excel uploads, using a shared set of validation and change-processing rules. Processing status and recoverable inputs make it possible to track outcomes and resume interrupted work.

The scope covers product identity, SKU, name, and active status. Stock quantities and warehouse operations are outside this project's scope.

## Run locally

Prerequisites: Python 3.12, PostgreSQL, and separate databases `CDMS` and `CDMS_Test`. Commands below use PowerShell from the repository root.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Edit `.env` with your PostgreSQL connection URL, including the exact database name. Do not commit credentials. Set `INVENTORY_BASE_URL=http://127.0.0.1:8000`, `POLLING_ENABLED=true`, and `POLLING_INTERVAL_SECONDS=30` for the polling demonstration.

```powershell
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`. In a second terminal, activate the environment and run:

```powershell
python -m app.workers.sync_worker
```

The sync worker runs continuously and holds a PostgreSQL singleton advisory lock. The emulator and CDMS APIs run in the same FastAPI application, with separate database schemas.

## Tests

Migrate the separate test database before running integration tests:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://<user>:<password>@127.0.0.1:5432/CDMS_Test"
$env:TEST_DATABASE_URL = $env:DATABASE_URL
python -m alembic upgrade head
python -m pytest -q -ra
Remove-Item Env:DATABASE_URL
Remove-Item Env:TEST_DATABASE_URL
```

Restart services after changing environment variables. See the test report for measured results and verification limits.

## Submission documents

- [Prototype explanation and demonstration](docs/demo-guide.md)
- [Implemented features and limitations](docs/implementation-status.md)
- [Lessons learned](docs/lessons-learned.md)
- [AI assistance disclosure](docs/ai-usage.md)
- [Test results and measurements](docs/test-report.md)
