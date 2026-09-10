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

"""Cloud Bigtable Real-Time Metrics Tool (read_cashier_realtime_metrics)."""

import json
import os
import re
import struct
import time
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from google.cloud import bigtable
from google.cloud.bigtable.row_set import RowSet

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"), override=True)

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "data-advanced-ruby")
INSTANCE_ID = os.getenv("BIGTABLE_INSTANCE", "operations-db")
TABLE_NAME = os.getenv("BIGTABLE_TABLE", "cashier_realtime_alerts")


def read_cashier_realtime_metrics(store_id: str, cashier_id: str) -> str:
    """Queries Cloud Bigtable operations-db for real-time 1-hour rolling metrics and audit status flags for a cashier.

    Use this tool when users ask for:
    - Real-time / live cashier metrics (1-hour rolling override rate, promo rate, transaction count)
    - Active real-time cashier risk score or audit status flags ('review' vs 'clear')
    - Current intraday live status for a specific cashier at a specific store (e.g., Cashier CASH_1190 at Store 48)

    Args:
        store_id: Store identifier, formatted as 'STORE_048' or integer '48' or '048'.
        cashier_id: Cashier identifier, formatted as 'CASH_1190' or '1190'.

    Returns:
        A structured JSON/markdown string detailing the most recent 1-hour rolling metrics,
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

    row_prefix = f"{norm_store}#{norm_cash}#"

    max_retries = 3
    backoff_factor = 2.0
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            client = bigtable.Client(project=PROJECT_ID, admin=False)
            instance = client.instance(INSTANCE_ID)
            table = instance.table(TABLE_NAME)

            row_set = RowSet()
            row_set.add_row_range_from_keys(
                start_key=row_prefix.encode("utf-8"),
                end_key=(f"{norm_store}#{norm_cash}$\xff").encode("utf-8"),
            )

            rows = list(table.read_rows(row_set=row_set, limit=1))
            if not rows:
                return (
                    f"No real-time alert or metric records found in Bigtable table `{TABLE_NAME}` "
                    f"for {norm_cash} at {norm_store} (prefix: {row_prefix})."
                )

            latest_row = rows[0]
            row_key_str = latest_row.row_key.decode("utf-8")
            metrics: Dict[str, Any] = {
                "store_id": norm_store,
                "cashier_id": norm_cash,
                "latest_row_key": row_key_str,
            }

            for cf, cols in latest_row.cells.items():
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

                    # Decode string or float fields
                    str_val = val_bytes.decode("utf-8", errors="ignore")
                    try:
                        if "." in str_val or "e" in str_val.lower():
                            metrics[col_name] = float(str_val)
                        else:
                            metrics[col_name] = int(str_val)
                    except ValueError:
                        metrics[col_name] = str_val

            # Compute manual override rate if count and txn_count are present
            txn_count = metrics.get("cashier_1h_txn_count", 0)
            override_cnt = metrics.get("cashier_1h_manual_override_count", 0)
            if txn_count and txn_count > 0:
                override_rate = round(override_cnt / txn_count, 4)
            else:
                override_rate = 0.0
            metrics["cashier_1h_manual_override_rate"] = override_rate

            return (
                f"### Real-Time Cashier Metrics (Cloud Bigtable: {INSTANCE_ID}.{TABLE_NAME})\n\n"
                f"- **Store:** {metrics['store_id']}\n"
                f"- **Cashier ID:** {metrics['cashier_id']}\n"
                f"- **Audit Status Flag:** `{metrics.get('audit_status', 'unknown')}`\n"
                f"- **Real-Time Risk Score:** {metrics.get('risk_score', 0.0)}\n"
                f"- **Live 1-Hour Rolling Override Rate:** {metrics.get('cashier_1h_manual_override_rate', 0.0):.2%} ({override_cnt}/{txn_count})\n"
                f"- **Live 1-Hour Rolling Promo Rate:** {float(metrics.get('cashier_1h_promo_rate', 0.0)):.2%} ({metrics.get('cashier_1h_promo_count', 0)} promos)\n"
                f"- **Live 1-Hour Total Discount (USD):** ${metrics.get('cashier_1h_total_discount_usd', '0.00')}\n"
                f"- **Last Event Timestamp:** {metrics.get('last_event_ts', 'N/A')}\n\n"
                f"```json\n{json.dumps(metrics, indent=2)}\n```"
            )
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                time.sleep(backoff_factor ** attempt)

    return f"Cloud Bigtable telemetry service unreachable. Error details: {last_error}"
