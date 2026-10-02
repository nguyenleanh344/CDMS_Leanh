# AI Assistance Disclosure

This disclosure is based on the candidate's account of the development process and the recorded AI-assisted review and reporting work.

## Candidate contribution

I implemented and iterated on the backend outside the Excel portion, including the database models and migrations, emulator, webhook flow, polling jobs, scheduler, and callback client. This work was AI-assisted through implementation guidance and review; I do not claim that it was completed without AI assistance. I configured the local environment, ran migrations and tests, and demonstrated the ingestion flows using Swagger and PostgreSQL.

## AI contribution

| Development activity | AI involvement |
| --- | --- |
| Initial requirement analysis | Helped interpret the assignment, identify business rules, and define the prototype scope |
| Design documents | Helped write the planning documents, including API contracts, payloads/responses/validation, business rules, ERD, user stories, technical design, and implementation plans |
| Project structure and phases | Helped propose the folder structure and divide implementation into phases |
| Guidance for each phase | Provided detailed explanations of how to implement each phase, including data flow, transactions, validation, and testing |
| Excel implementation | I requested AI-generated code for the Excel portion because of its complexity; this portion must be attributed as AI-generated/AI-assisted rather than solely candidate-written |
| Review after implementation | Reviewed code after each phase, identified errors, and suggested fixes and additional checks |
| Debugging | Assisted with migration/configuration issues, API validation, test isolation, Excel foreign-key insertion order, and the Windows pytest parameter-ID issue |

The Excel attribution covers the Excel implementation as a feature. The exact boundary between generated code, candidate edits, and related tests has not been audited line by line. Other modules also received AI guidance, reviews, and some implementation suggestions, so candidate implementation does not imply exclusive authorship of every line.
