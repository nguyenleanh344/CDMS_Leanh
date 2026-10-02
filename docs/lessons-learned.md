# Lessons Learned

## Planning made the implementation more manageable

I received the assignment at approximately 10:00 AM on the first day, with a two-day deadline. I did not immediately start coding. I spent the day analyzing the requirements and preparing detailed documents, and started writing the first implementation code at approximately 8:00 PM. By the end of the following day, the prototype was largely complete.

The planning covered business rules, API payloads and responses, validation, the ERD, user stories, folder structure, and implementation phases. I used AI assistance during this process, as disclosed in the AI usage document. My main lesson was that the value of planning came from resolving concrete questions before they spread into code: what identifies a product, what counts as a change, how versions are compared, and how each ingestion channel maps into the same data model.

An incorrect assumption in a document was quick to revise. The same assumption implemented in several endpoints, database tables, migrations, and tests would have required more rework. Spending time on the design initially felt expensive under a short deadline, but it gave me a clearer sequence of implementation tasks and reduced the number of decisions I had to make while coding. This is my experience from this prototype, rather than a claim that every project needs the same amount of upfront documentation.

## Use AI to support understanding and planning

AI was useful to me beyond generating code. It helped break down the assignment, identify questions and assumptions, compare possible designs, and turn the requirements into business rules, API contracts, an ERD, user stories, and an implementation plan. Working through the requirements alone would likely have taken me longer, especially under the two-day deadline. That is my assessment of this experience, not a measured comparison.

However, having AI produce a document is not the same as understanding or approving its design. I needed to read the documents, compare them with the original assignment, and ask follow-up questions whenever a concept or flow was unclear. Questions about webhook versus polling, jobs versus events, and lease-based recovery helped me understand the choices rather than simply reproduce them. I learned to keep asking until I could explain the behavior in my own words.

AI suggestions can sound convincing while relying on assumptions that do not match the task. For example, the meaning of a source version, the scope of product data, and the difference between a custom snapshot callback and the referenced inventory webhook all needed explicit review. A detailed plan is only useful when its assumptions are understood and checked.

The final decision had to remain mine: what scope to commit to, which suggestions to accept or revise, and what the prototype could honestly claim to support. AI helped me reach those decisions, but did not replace my responsibility to understand the implementation, verify its behavior, and explain its limitations. In a future task, I would also establish the permitted use of AI before starting and stay within those boundaries; the assistance used here is disclosed separately.

## Define data decisions before defining endpoints

The three ingestion channels initially look like separate features. However, each ultimately provides a product snapshot that must be compared with the current state. I learned to define that comparison first and then let webhook, polling, and Excel feed the same processor.

| Incoming data | Required decision |
| --- | --- |
| Product does not exist | Create current state and an initial change |
| Older version | Keep current state; mark the input stale |
| Same version and same content | Recognize a duplicate |
| Same version and different content | Report a conflict instead of silently overwriting |
| Newer version and same content | Advance the current version without adding a content change |
| Newer version and different content | Update current state and append a change |

This decision table provided a concrete contract for implementation and tests. It also clarified why a version increase is not necessarily a business change, and why returning from content A to B to A must still create a new change when the version increases. Comparing with the current content preserves that transition; globally rejecting a previously seen content hash would lose it.

I also learned to make source assumptions explicit. Version ordering only makes sense when all channels share one logical source and its version convention. The emulator version is a prototype extension, and Excel upload time must not turn an old snapshot into new source data. Polling can capture the snapshots it observes, but cannot reconstruct intermediate changes it never received.

## Separate received input, processing progress, and business state

The tables became easier to understand once I assigned each a specific responsibility. A processing job represents a batch or synchronization attempt. An inbound event preserves an individual input and its outcome. Product current represents the latest accepted state, while product changes records meaningful accepted content changes.

This separation lets a rejected Excel row remain traceable without modifying product state. It also lets a batch complete with partial success instead of discarding valid rows because another row is invalid. Persisted input makes it possible to resume processing without fetching a different source snapshot for the same job, although automatic recovery still depends on the worker implementation and its lease rules.

Request identity and content equality also need separate treatment. A request fingerprint detects reuse of the same external event ID with a different request. A business hash detects whether product content changed. Treating them as interchangeable would mix transport retries with product history decisions.

## Turn the plan into small, testable phases

Dividing the work into phases helped me keep a working path through the system: schema and migrations, emulator, webhook and shared processor, polling, Excel, scheduling, and demonstration scripts. At each phase, I could inspect the API result and database state before adding another entry point.

User stories and acceptance criteria were most useful when they named observable outcomes. For example, “an older snapshot cannot overwrite current state” is something I can test across all channels. A folder tree helped locate responsibilities, but the data flow and acceptance criteria were what helped establish correctness.

The documents were working hypotheses rather than proof. Migrations and PostgreSQL integration tests still had to verify that constraints, transaction boundaries, and recovery paths behaved as intended. I learned to revise both the implementation and its documentation when the actual behavior differed from the plan.

## Implementation exposed details that design alone did not catch

Excel import exposed a foreign-key violation when events were inserted before their processing job. Flushing the parent job first satisfied the foreign key while keeping acceptance in one transaction. A manually uploaded spreadsheet also showed that a displayed ID such as `01` can be stored as text; strict validation and preserved raw input made the cause visible.

For tests, a dedicated PostgreSQL database and rollback-based fixtures allowed repeatable verification without manually deleting application data. Another issue came from pytest using a 5 MiB payload as a parameterized test name, exceeding a Windows environment-variable limit. Short explicit IDs fixed the test infrastructure without weakening the upload-size check.

These issues reinforced that a good plan reduces uncertainty but does not eliminate the need to execute, inspect, and test the system.

## Report what was demonstrated, including the limits

The final review also taught me to distinguish intended architecture from implemented behavior. The channels share a processor, but webhook processing currently runs inside the request, Excel uses a background task, and polling uses a continuous worker. The prototype does not yet have a continuous unified worker for all channels.

Likewise, the measured webhook response time includes processing. It is not evidence of asynchronous backlog throughput. Passing automated retry/resume simulations is not equivalent to testing a real worker crash and restart. Recording those distinctions made the report more accurate and gave me a concrete list of improvements for a future iteration.
