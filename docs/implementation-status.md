# Implementation Status

| Feature | Status | Evidence or limitation |
| --- | --- | --- |
| Python/FastAPI backend and Swagger | Implemented | REST API demonstration |
| PostgreSQL schemas and Alembic migrations | Implemented | Emulator and CDMS schemas |
| Product emulator and Faker seed script | Implemented | Product create/read/update and seed command |
| Callback client | Implemented | Fetches emulator snapshot and sends webhook |
| Webhook acceptance and idempotency | Implemented | Processing is synchronous within the request |
| Scheduled and manual polling | Implemented | Interval loop and singleton lock; automated scheduler tests |
| Excel acceptance, row validation, batch status/errors | Implemented | Parser and PostgreSQL integration tests |
| Shared version/content decisions and history | Implemented | Automated decision tests |
| Polling retry and resume after input persistence | Implemented | Automated failure/resume simulations |
| Small sequential HTTP load test | Verified | 100 successful events and 100 replays; see test report |
| Live crash/restart and concurrent load verification | Not completed | Not measured in the recorded run |
| Continuous unified worker for all channels | Not completed | Sync loop, inline webhook processor, Excel background task/one-shot recovery |
| Full Vietful API compatibility | Outside prototype scope | Product subset and custom snapshot callback |
| Stock quantities, multiple warehouses, inventory deltas | Outside prototype scope | Product metadata only |
| Frontend | Not required | Swagger and scripts used |
| Docker deployment | Not completed | Local PostgreSQL setup is the documented path |

## Operational limits

- Default sync requests cap the scan at 1,000 products. This is not an unlimited full scan.
- PROCESSING jobs use a one-hour lease before recovery selection.
- Excel limits are 5 MiB and 10,000 data rows.
- A polling scan is not an atomic source snapshot across all pages. Count consistency checks cannot detect every concurrent source modification.
- Durable inbound records alone do not guarantee automatic recovery for every channel. A continuous webhook recovery loop is not implemented.
- Authentication, production monitoring, deployment hardening, and production capacity validation are not claimed.

The reported automated run passed 80 tests. Passing tests establish the tested behavior, not production readiness or untested process-failure guarantees.
