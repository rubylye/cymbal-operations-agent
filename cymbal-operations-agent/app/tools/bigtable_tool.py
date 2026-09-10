# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Cloud Bigtable Declarative SQL & Real-Time Metrics Tools with MCP Toolbox Gateway."""

import json
import os
import re
import struct
import time
from typing import Any

import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.cloud import bigtable
from google.cloud.bigtable.row_set import RowSet
from google.oauth2 import id_token

from app.utils.pii_masking import mask_pii_data

load_dotenv(
    dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
    override=True,
)

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("PROJECT_ID", ""))
INSTANCE_ID = os.getenv("BIGTABLE_INSTANCE", "operations-db")
TABLE_NAME = os.getenv("BIGTABLE_TABLE", "cashier_realtime_alerts")
BIGTABLE_MCP_URL = os.getenv("BIGTABLE_MCP_URL", "")


def _query_via_mcp_toolbox(tool_name: str, arguments: dict[str, Any]) -> str | None:
    """Attempts to query the Cloud Run Bigtable MCP microservice executing declarative GoogleSQL tools."""
    if not BIGTABLE_MCP_URL:
        return None
    try:
        req = Request()
        token = id_token.fetch_id_token(req, BIGTABLE_MCP_URL)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "name": tool_name,
            "arguments": arguments,
        }
        resp = requests.post(
            f"{BIGTABLE_MCP_URL.rstrip('/')}/tools/{tool_name}/invoke",
            headers=headers,
            json=payload,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "result" in data:
                return str(mask_pii_data(data["result"]))
            return json.dumps(mask_pii_data(data), indent=2)
    except Exception:
        pass
    return None


def read_cashier_realtime_alerts_sql(store_id: str, cashier_id: str) -> str:
    """Executes declarative GoogleSQL over Bigtable instance operations-db to query real-time 1-hour rolling metrics and cashier anomaly alerts.

    Use this tool when users ask for:
    - Real-time / live cashier metrics (1-hour rolling override rate, promo rate, transaction count)
    - Active real-time cashier risk score or audit status flags ('review' vs 'clear')
    - Current intraday live status for a specific cashier at a specific store (e.g., Cashier CASH_1190 at Store 48)

    Args:
        store_id: Store identifier, formatted as 'STORE_048' or integer '48' or '048'.
        cashier_id: Cashier identifier, formatted as 'CASH_1190' or '1190'.

    Returns:
        A structured JSON string detailing the most recent 1-hour rolling metrics,
        audit status, risk score, and transaction statistics.
    """
    # Normalize store_id (e.g. 48 -> STORE_048, STORE_48 -> STORE_048)
    store_num = re.findall(r"\d+", str(store_id))
    if store_num:
        norm_store = f"STORE_{int(store_num[0]):03d}"
    else:
        norm_store = str(store_id).strip()

    # Normalize cashier_id (e.g. 1190 -> CASH_1190)
    cash_num = re.findall(r"\d+", str(cashier_id))
    if cash_num:
        norm_cash = f"CASH_{cash_num[0]}"
    else:
        norm_cash = str(cashier_id).strip()

    # Step 1: Attempt Centralized MCP Microservice Call
    mcp_result = _query_via_mcp_toolbox(
        "read_cashier_realtime_alerts_sql",
        {"store_id": norm_store, "cashier_id": norm_cash},
    )
    if not mcp_result:
        mcp_result = _query_via_mcp_toolbox(
            "read_cashier_realtime_metrics",
            {"store_id": norm_store, "cashier_id": norm_cash},
        )
    if mcp_result:
        return mcp_result

    # Step 2: Resilient Local Execution
    row_prefix = f"{norm_store}#{norm_cash}#"
    max_retries = 3
    backoff_factor = 2.0

    for attempt in range(1, max_retries + 1):
        try:
            client = bigtable.Client(project=PROJECT_ID, admin=False)
            instance = client.instance(INSTANCE_ID)
            table = instance.table(TABLE_NAME)

            row_set = RowSet()
            row_set.add_row_range_from_prefix(row_prefix.encode("utf-8"))

            rows = list(table.read_rows(row_set=row_set, limit=10))

            if not rows:
                return json.dumps(
                    {
                        "store_id": norm_store,
                        "cashier_id": norm_cash,
                        "temporal_scope": "live_rolling_1h",
                        "valid_for_minutes": 60,
                        "status": "NO_ALERTS",
                        "message": f"No active live 1-hour cashier alerts found for {norm_cash} at {norm_store} (prefix: {row_prefix}).",
                    },
                    indent=2,
                )

            latest_row = rows[0]
            row_key_str = latest_row.row_key.decode("utf-8")
            metrics: dict[str, Any] = {
                "store_id": norm_store,
                "cashier_id": norm_cash,
                "latest_row_key": row_key_str,
                "temporal_scope": "live_rolling_1h",
                "valid_for_minutes": 60,
            }

            for _cf, cols in latest_row.cells.items():
                for col_name_b, cell_list in cols.items():
                    col_name = col_name_b.decode("utf-8")
                    val_bytes = cell_list[0].value

                    # Decode int64 Bigtable counter fields
                    if len(val_bytes) == 8 and col_name in {
                        "cashier_1h_manual_override_count",
                        "cashier_1h_promo_count",
                        "cashier_1h_txn_count",
                    }:
                        try:
                            int_val = struct.unpack(">q", val_bytes)[0]
                            metrics[col_name] = int_val
                            continue
                        except Exception:
                            pass

                    # Decode string / float / bool fields
                    try:
                        str_val = val_bytes.decode("utf-8")
                        try:
                            if "." in str_val:
                                metrics[col_name] = float(str_val)
                            elif str_val.isdigit() or (
                                str_val.startswith("-") and str_val[1:].isdigit()
                            ):
                                metrics[col_name] = int(str_val)
                            elif str_val.lower() in ("true", "false"):
                                metrics[col_name] = str_val.lower() == "true"
                            else:
                                metrics[col_name] = str_val
                        except ValueError:
                            metrics[col_name] = str_val
                    except UnicodeDecodeError:
                        metrics[col_name] = f"0x{val_bytes.hex()}"

            # Compute derived ratios if missing
            txn_count = metrics.get("cashier_1h_txn_count", 0)
            if (
                isinstance(txn_count, (int, float))
                and txn_count > 0
                and "cashier_1h_override_rate" not in metrics
            ):
                ovr = metrics.get("cashier_1h_manual_override_count", 0)
                metrics["cashier_1h_override_rate"] = round(
                    float(ovr) / float(txn_count), 4
                )

            if (
                isinstance(txn_count, (int, float))
                and txn_count > 0
                and "cashier_1h_promo_rate" not in metrics
            ):
                prm = metrics.get("cashier_1h_promo_count", 0)
                metrics["cashier_1h_promo_rate"] = round(
                    float(prm) / float(txn_count), 4
                )

            return json.dumps(mask_pii_data(metrics), indent=2)

        except Exception:
            if attempt < max_retries:
                time.sleep(backoff_factor**attempt)

    return json.dumps(
        {
            "status": "ERROR",
            "message": "Regional operational telemetry is temporarily unreachable",
        },
        indent=2,
    )


def read_pos_transactions_enriched_sql(
    store_id: str, transaction_id: str = "", limit_count: int = 10
) -> str:
    """Executes declarative GoogleSQL over Bigtable instance operations-db to query enriched sub-second POS checkout transactions with PII masking.

    Args:
        store_id: Store identifier (e.g. STORE_048 or 48).
        transaction_id: Optional POS transaction ID to look up.
        limit_count: Maximum number of records to return (default: 10).

    Returns:
        A structured JSON string with enriched transaction details, masking customer payment card numbers.
    """
    store_num = re.findall(r"\d+", str(store_id))
    norm_store = (
        f"STORE_{int(store_num[0]):03d}" if store_num else str(store_id).strip()
    )

    # Step 1: Attempt Centralized MCP Microservice Call
    mcp_result = _query_via_mcp_toolbox(
        "read_pos_transactions_enriched_sql",
        {
            "store_id": norm_store,
            "transaction_id": transaction_id,
            "limit_count": limit_count,
        },
    )
    if mcp_result:
        return mcp_result

    # Step 2: Resilient Local Execution
    prefix = f"{norm_store}#{transaction_id}" if transaction_id else f"{norm_store}#"
    try:
        client = bigtable.Client(project=PROJECT_ID, admin=False)
        instance = client.instance(INSTANCE_ID)
        table = instance.table("pos_transactions_enriched")

        row_set = RowSet()
        row_set.add_row_range_from_prefix(prefix.encode("utf-8"))
        rows = list(table.read_rows(row_set=row_set, limit=limit_count))

        results = []
        for r in rows:
            record: dict[str, Any] = {"row_key": r.row_key.decode("utf-8")}
            for _cf, cols in r.cells.items():
                for c_name, c_list in cols.items():
                    col = c_name.decode("utf-8")
                    val = c_list[0].value.decode("utf-8", errors="ignore")
                    record[col] = val
            results.append(mask_pii_data(record))

        return json.dumps(
            {
                "store_id": norm_store,
                "record_count": len(results),
                "transactions": results,
            },
            indent=2,
        )
    except Exception:
        return json.dumps(
            {
                "status": "ERROR",
                "message": "Regional operational telemetry is temporarily unreachable",
            },
            indent=2,
        )


# Backward-compatible alias for existing imports
read_cashier_realtime_metrics = read_cashier_realtime_alerts_sql
