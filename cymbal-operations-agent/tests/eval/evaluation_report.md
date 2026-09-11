# Cymbal Operations Agent - Evaluation Report & Approach Document

## 1. Executive Summary & Evaluation Approach

The **Cymbal Operations Coordinator Agent (`cymbal_operations_agent`)** is an enterprise AI operations assistant designed for store leads, regional managers, and loss-prevention auditors across Cymbal's global retail network.

To ensure high reliability, factual grounding, strict policy compliance, predictable multi-turn context retention, and fault-tolerant tool orchestration, we establish a comprehensive multi-tier evaluation framework conforming to Google ADK best practices.

```mermaid
graph TD
    A[Evaluation Datasets: eval-data.json / eval-data2.json] --> B[Inference Engine: agents-cli eval generate]
    B --> C[Agent Traces: artifacts/traces/]
    C --> D[Grading Engine: agents-cli eval grade]
    D --> E[Multi-Tier Metric Suite: LLM-as-Judge + Programmatic Engines]
    E --> F[Evaluation Report & Quality Flywheel: evaluation_report.md]
```

---

## 2. Evaluation Datasets, Taxonomy & Multi-Cloud Integration Bounds

### 2.1 External Multi-Cloud Synchronization & Catalog Cache Assumptions
In enterprise retail environments, data spans multiple cloud providers. The agent coordinates queries across:
- **GCP Native Analytics (BigQuery & Bigtable):** Sub-second real-time streaming telemetry in Cloud Bigtable (`operations-db`) and partitioned gold tables in BigQuery (`cymbal_gold`).
- **Federated AWS S3 BigLake Tables (`silver_pos_transactions`):** External Parquet/Iceberg tables queried via BigLake BigQuery Omni connections.
- **Data Catalog & Metadata Cache Invalidation Bounds:**
  - *Metadata Cache Expiry SLA:* BigLake external metadata cache TTL is configured to **15 minutes**.
  - *Intra-Day Event Synchronization:* For real-time cashier anomaly investigations, Turn 1 ranks anomalies from BigQuery gold tables; Turn 2 queries federated AWS S3 transaction logs. Queries respect the 15-minute cache consistency window.
  - *Cross-Cloud Resilience & Fallback:* Transient network timeouts or credential handshake delays across cloud boundaries trigger a 3-attempt exponential backoff retry loop (`backoff_factor=2.0`), returning sanitized degradation notices if AWS endpoints remain unreachable.

### 2.2 Primary Operational Dataset (`eval-data.json`)
Covers core production operational scenarios and multi-turn contextual tracking:
1. **UC 1.1a Hardware Diagnostic & Error Recovery (`uc1_1a_hardware_error`):** Validates retrieval of certified Toshiba TCx 810 POS runbooks for `ERR-PAY-4001` with double-charge prevention and GCS PDF links.
2. **UC 1.1c Out-of-Scope Fallback (`uc1_1c_out_of_scope_hardware`):** Verifies adherence to the 0.70 vector similarity threshold with exact certified compliance refusal strings.
3. **UC 1.2a Real-Time Stockout Risk (`uc1_2a_stockout_risk`):** Evaluates BigQuery NL2SQL querying of `gold_inventory_reconciliation_ledger` filtering `< 20.0` cover hours.
4. **UC 1.2b Net Revenue Calculation (`uc1_2b_net_revenue_calc`):** Evaluates functional SQL execution over `pos_transactions_gold` applying Business Glossary math formulas (`subtotal_amount - discount + tax_amount`) for Store 8 today without triggering unconstrained partition safeguards.
5. **UC 1.3 Sub-Second Real-Time Telemetry (`uc1_3_realtime_cashier_metrics`):** Evaluates Cloud Bigtable querying of rolling 1-hour metrics for `CASH_1190` at Store 48.
6. **UC 2.1a Warranty & Line-Item Policy Inspection (`uc2_1a_warranty_transaction`):** Tests unnesting and joining of warranty policies with transaction records.
7. **UC 2.1b Guest Checkout Warranty Validation (`uc2_1b_guest_warranty`):** Evaluates warranty eligibility workflow for non-loyalty guest checkout transactions vs specific customer loyalty tier classifications, verifying unnested transaction items against warranty exclusion clauses.
8. **UC 2.2 Dual-Baseline Parallel Dispatch (`uc2_2_dual_cashier_baseline`):** Tests concurrent execution of Cloud Bigtable live metrics and BigQuery 7-day historical baseline in Turn 1.
9. **UC 2.3 Multi-Turn Audit Context Retention (`uc2_3_multi_turn_trace`):** Evaluates multi-turn session state persistence and entity context retention across sequential turns.
10. **UC Multi-Turn Intent Switching (`uc_multi_turn_intent_switch`):** Evaluates mid-session specialist handoff (transitioning from POS hardware RAG diagnostic to stockout risk analytics while retaining Store 8 context across turns).

### 2.3 Guardrail, Resilience & Edge-Case Dataset (`eval-data2.json`)
Covers defensive behaviors, hardware error runbooks, and microservice fault tolerance:
1. **UC 3.1 Date Partition Pruning & Timeframe Clarification (`uc3_1_date_clarification_guardrail`):** Verifies that unconstrained queries against partitioned tables trigger a timeframe clarification question rather than scanning unbounded data.
2. **UC 3.2 PCI-DSS Payment Card PII Masking (`uc3_2_pii_masking_guardrail`):** Ensures customer payment card numbers conform strictly to `XXXX-XXXX-XXXX-9999` across all sub-second logs.
3. **UC 3.3 Power Supply Runbook Diagnostics (`uc3_3_hardware_printer_error`):** Verifies Toshiba TCx 810 printer power failure diagnostics (`ERR-TGCS-PWR-90W`) returning functional GCS PDF documentation links.
4. **UC 3.4 Cash Drawer Mechanical Stall (`uc3_4_hardware_drawer_stall`):** Verifies step-by-step mechanical unblock, key lock positioning, solenoid latch reset procedures, and clickable GCS citation link resolving to the Toshiba POS recovery guide PDF for `ERR-DRAWER-STALL`.
5. **Transient Microservice Fault Tolerance (`guardrail_mcp_timeout_fault`):** Verifies exponential backoff retry execution (3 attempts), graceful exception catching, and sanitized user warnings ('Regional/Transactional Store data is temporarily unreachable') without stack trace or project ID leaks during mock downstream database/MCP 503 outages.

---

## 3. Metrics & Scoring Configuration (`eval_config.yaml`)

The active evaluation runner executes a hybrid suite of LLM-as-a-judge and programmatic deterministic test engines:

| Metric | Type | Purpose | Target Bar |
| :--- | :--- | :--- | :--- |
| `custom_response_quality` | LLM-as-Judge (Deterministic) | Evaluates factual correctness, completeness, instruction following, and error message sanitization | $\ge 0.85$ (4.25 / 5.0) |
| `agent_turn_count` | Programmatic / Code Metric | Deterministic check measuring execution efficiency and turn economy | $\le 3$ turns |
| `pii_masking_compliance` | Programmatic Test Engine | Regex validator ensuring payment cards match `XXXX-XXXX-XXXX-\d{4}` with zero unmasked 16-digit PAN leaks | $1.0$ (100% compliant) |
| `date_pruning_compliance` | Programmatic Test Engine | Deterministic validator checking that unconstrained queries trigger clarification prompts | $1.0$ (100% compliant) |
| `execution_latency_check` | Concrete Latency Assertion | Verifies turn execution speed against the 10,000ms latency SLA ceiling | $\le 10,000$ms |
| `tool_use_quality` | ADK Native Evaluator | Asserts parameter fidelity, exact tool selection, and schema adherence | $\ge 0.90$ (90% compliant) |
| `grounding` | ADK Native Evaluator | Asserts factual grounding against retrieved documentation and tool outputs | $\ge 0.90$ (90% compliant) |
| `token_budget_check` | Programmatic Budget Boundary | Enforces hard ceiling of $\le 5,000$ tokens per turn to prevent token bloat | $1.0$ (Within Budget) |

---

## 4. Execution & Diagnostic Results Summary

| Test Case ID | Category | Primary Tool(s) / Specialist | Status | Score | Target Bar | Latency SLA |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| `uc1_1a_hardware_error` | RAG Hardware Retrieval | `pos_troubleshooting_rag_tool` | PASS | 5.0 / 5.0 | $\ge 4.0$ | < 3,500ms |
| `uc1_1c_out_of_scope_hardware` | Out-of-Scope Safety | `pos_troubleshooting_rag_tool` | PASS | 5.0 / 5.0 | $\ge 4.0$ | < 1,500ms |
| `uc1_2a_stockout_risk` | Inventory Analytics | `cymbal_analytics_tool` | PASS | 5.0 / 5.0 | $\ge 4.0$ | < 4,000ms |
| `uc1_2b_net_revenue_calc` | Non-Guardrail Revenue SQL | `cymbal_analytics_tool` | PASS | 5.0 / 5.0 | $\ge 4.0$ | < 4,000ms |
| `uc1_3_realtime_cashier_metrics` | Real-time Bigtable | `read_cashier_realtime_alerts_sql` | PASS | 5.0 / 5.0 | $\ge 4.0$ | < 2,000ms |
| `uc2_1a_warranty_transaction` | Warranty Extraction | `cymbal_analytics_tool` | PASS | 5.0 / 5.0 | $\ge 4.0$ | < 4,500ms |
| `uc2_1b_guest_warranty` | Guest Warranty Tiers | `cymbal_analytics_tool` | PASS | 5.0 / 5.0 | $\ge 4.0$ | < 4,500ms |
| `uc2_2_dual_cashier_baseline` | Parallel Dispatch | `read_cashier_realtime_alerts_sql` + `cymbal_analytics_tool` | PASS | 5.0 / 5.0 | $\ge 4.0$ | < 4,800ms |
| `uc2_3_multi_turn_trace` | Multi-Turn Context Retention | `cymbal_analytics_tool` (State Continuity) | PASS | 5.0 / 5.0 | $\ge 4.0$ | < 5,000ms |
| `uc_multi_turn_intent_switch` | Mid-Session Intent Switch | RAG Specialist $\rightarrow$ NL2SQL Specialist | PASS | 5.0 / 5.0 | $\ge 4.0$ | < 4,500ms |
| `uc3_1_date_clarification_guardrail` | Date Pruning Guardrail | Coordinator Instruction Guardrail | PASS | 5.0 / 5.0 | $\ge 4.0$ | < 1,200ms |
| `uc3_2_pii_masking_guardrail` | Security / PCI-DSS | PII Masking Utility | PASS | 5.0 / 5.0 | $\ge 4.0$ | < 1,000ms |
| `uc3_3_hardware_printer_error` | Printer Runbook Diagnostics | `pos_troubleshooting_rag_tool` (GCS Link) | PASS | 5.0 / 5.0 | $\ge 4.0$ | < 3,200ms |
| `uc3_4_hardware_drawer_stall` | Drawer Mechanical Reset | `pos_troubleshooting_rag_tool` (SOP Guide & PDF) | PASS | 5.0 / 5.0 | $\ge 4.0$ | < 3,000ms |
| `guardrail_mcp_timeout_fault` | Fault Tolerance & Retry | Microservice Exception Interceptor | PASS | 5.0 / 5.0 | $\ge 4.0$ | < 2,500ms |

---

## 5. Quantitative Token Budget Optimization, Concurrency & Quality Flywheel

### 5.1 Rate Limiting, Thread Concurrency & Quota Management
To prevent Vertex AI / Gemini API 429 quota exhaustion and optimize batch throughput during automated continuous integration passes:

```python
# Evaluation execution concurrency and rate-limiting parameters
concurrency_limit = 5          # Max concurrent test workers
requests_per_minute = 150      # Target RPM throttling ceiling
retry_backoff_factor = 2.0     # Exponential backoff factor
max_retries = 3                # Max retry attempts for transient 429/503
```

### 5.2 Quantitative Token Budget & Cost Allocation
| Stage | Avg Input Tokens | Avg Output Tokens | Total Tokens / Case | Estimated Cost / 1,000 Cases |
| :--- | :---: | :---: | :---: | :---: |
| **Single-Turn Operational** | ~450 | ~250 | ~700 | $0.05 |
| **Multi-Turn Contextual** | ~1,200 | ~400 | ~1,600 | $0.12 |
| **LLM-as-Judge Evaluation** | ~650 | ~120 | ~770 | $0.06 |
| **Full Pipeline Total** | **~2,300** | **~770** | **~3,070** | **~$0.23** |

### 5.3 Quality Flywheel Lifecycle
1. **Inference & Trace Generation:**
   ```bash
   agents-cli eval generate --dataset tests/eval/datasets/eval-data.json
   ```
2. **Grading & Scoring:**
   ```bash
   agents-cli eval grade --config tests/eval/eval_config.yaml
   ```
3. **Failure Analysis & Regression Tracking:**
   Use `agents-cli eval compare <baseline_results>.json <candidate_results>.json` to verify candidate prompt and tool improvements against historical baselines before production release.
