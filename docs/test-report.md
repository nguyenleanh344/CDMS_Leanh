# Test Report

Date: 2026-10-01 (Asia/Saigon).

## Automated verification

Executed using the project's virtual environment against PostgreSQL database `CDMS_Test`:

```powershell
python -m pytest -q -ra
```

Result: **80 passed**, no failures, errors, or skipped tests. Command wall time was approximately 7.19 seconds (includes process startup). One Starlette TestClient/httpx deprecation warning remains.

The suite covers emulator operations, webhook ingestion and idempotency, product version decisions, Excel parsing/import, polling jobs, and scheduler behavior. Recovery tests use a simulated unavailable inventory client and simulated interrupted job state; these are not measurements of a live process crash.

## Live HTTP smoke/load measurement

A separate Uvicorn process was started on `127.0.0.1:8017`, using `CDMS_Test`, with scheduled polling disabled. Requests were sent sequentially using PowerShell. The normal development API was not stopped.

Run identifier: `report-9da87661891649b2842df16297d385f8`.

| Measurement | Observed result |
| --- | --- |
| Emulator products created through HTTP | 100 |
| Product creation duration | 1.350 seconds |
| New webhook requests | 100 |
| HTTP responses | 100 responses with status 202 |
| Webhook request duration | 4.657 seconds |
| Event states checked through GET API | 100 SUCCESS |
| Identical webhook replays | 100 |
| Responses indicating replay | 100 |
| Replay request duration | 0.704 seconds |

Each webhook included the product snapshot returned by the emulator creation API. Replays reused the exact payload and external event ID.

The current webhook service invokes `ProductProcessor` synchronously before returning its response. Consequently, response duration includes processing; this experiment does not measure an asynchronous queue's acceptance rate or backlog drain time. It is a sequential smoke/load measurement, not a concurrency benchmark. Replay responses and successful event states were verified; independent SQL counts of current/history were not measured in this run.

The 100 source products and associated CDMS records remain in `CDMS_Test` for inspection. They can be identified by the run identifier in their SKU and external event ID.

## Recovery evidence and remaining checks

Automated tests exercise fetch failure/retry exhaustion and resume with persisted input without fetching it again. Scheduler tests exercise interval decisions and simulated singleton-lock acquisition.

The following live scenarios were **not executed** during this measurement:

- Inventory API shutdown followed by recovery of the same job.
- Worker process termination during processing and lease-based recovery.
- Two actual worker processes competing for the PostgreSQL singleton lock.
- Concurrent webhook load and a separate backlog drain measurement.

The processing lease is currently one hour. A job left in PROCESSING after a crash may therefore wait for lease expiry before recovery. These limitations should be distinguished from the passing automated recovery tests.
