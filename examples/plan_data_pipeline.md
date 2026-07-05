# Data Pipeline — Engineering Plan

- Extract all records from the raw CSV export.
- Rename the columns to the canonical schema.
- Validate each row against the type spec and drop malformed rows.
- Summarize the daily ingestion volume into a one-paragraph note.
- Implement the deduplication logic across multiple source files.
- Refactor the transform module and update all call sites.
- Integrate the pipeline with the warehouse database and the CI workflow.
- Design a fault-tolerant, distributed backfill strategy for historical data.
- Reason about the subtle race condition in the concurrent writer.
- Document the runbook for on-call engineers.
