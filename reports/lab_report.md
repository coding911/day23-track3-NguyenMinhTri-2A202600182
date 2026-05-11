# Day 08 Lab Report

## 1. Student
- Name: Nguyễn Minh Trí
- Repo: https://github.com/coding911/day23-track3-NguyenMinhTri-2A202600182
- Date: 11/05/2026

## Metrics summary

- Total scenarios: 7
- Success rate: 100.00%
- Average nodes visited: 6.57
- Total retries: 4
- Total interrupts: 2

## 2. Architecture

The graph is built with a typed state and explicit node boundaries. It uses keyword-based classification to map queries into `simple`, `tool`, `missing_info`, `risky`, or `error` routes. Risky routes require approval, tool routes may retry on transient failures, and error routes can dead-letter after retry exhaustion.

## 3. State schema

| Field | Reducer | Why |
|---|---|---|
| messages | append | audit and workflow tracing |
| tool_results | append | preserve tool outputs across retries |
| errors | append | record retry and failure history |
| events | append | audit log for every node transition |
| route | overwrite | current route classification |
| attempt | overwrite | current retry attempt count |
| max_attempts | overwrite | retry budget |
| final_answer | overwrite | final user-facing response |
| approval | overwrite | approval decision payload |

## 4. Scenario results

| Scenario | Expected route | Actual route | Success | Retries | Interrupts |
|---|---|---|---:|---:|---:|
| S01_simple | simple | simple | True | 0 | 0 |
| S02_tool | tool | tool | True | 0 | 0 |
| S03_missing | missing_info | missing_info | True | 0 | 0 |
| S04_risky | risky | risky | True | 0 | 1 |
| S05_error | error | error | True | 3 | 0 |
| S06_delete | risky | risky | True | 0 | 1 |
| S07_dead_letter | error | error | True | 1 | 0 |

## 5. Failure analysis

1. Retry failures: Transient tool failures are detected by the evaluation node, which sets `needs_retry`. The retry node increments `attempt` and eventually routes to `dead_letter` when `max_attempts` is reached.
2. Risky actions: Risky queries are routed through a dedicated approval node. Approval is mocked in CI but can be switched to real HITL via `LANGGRAPH_INTERRUPT=true`.

## 6. Persistence / recovery evidence

This lab supports a persistence adapter through `src/langgraph_agent_lab/persistence.py`. It can use `memory` or `sqlite` checkpointers and preserves `thread_id` per run.

## 7. Extension work

- Implemented SQLite persistence support with `configs/lab-sqlite.yaml`.
- Verified SQLite-backed scenario execution and metrics generation with `outputs/metrics-sqlite.json`.
- Added report content that describes persistence, retry loops, and approval flow.

## 8. Improvements

The implementation can be extended with real external tool adapters, a more robust natural-language classifier, and a production-grade HITL approval flow.
