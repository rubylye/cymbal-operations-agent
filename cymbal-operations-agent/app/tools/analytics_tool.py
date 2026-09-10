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

"""NL2SQL Data Agent Tool (cymbal_analytics_tool) wrapping BigQuery Conversational Data Agent."""

import json
import os
import time

import google.auth
from google.adk.tools.data_agent.config import DataAgentToolConfig
from google.adk.tools.data_agent.data_agent_tool import ask_data_agent
from google.auth.transport.requests import Request

from app.utils.pii_masking import mask_pii_data, mask_pii_text

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("PROJECT_ID", ""))
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
DATA_AGENT_ID = os.getenv("BIGQUERY_DATA_AGENT_ID", "")

DATA_AGENT_NAME = os.getenv(
    "BIGQUERY_DATA_AGENT_NAME",
    f"projects/{PROJECT_ID}/locations/{LOCATION}/dataAgents/{DATA_AGENT_ID}"
    if PROJECT_ID and DATA_AGENT_ID
    else "",
)
BASE_URL = os.getenv(
    "GDA_BASE_URL",
    f"https://geminidataanalytics.{LOCATION}.rep.googleapis.com/v1beta"
    if LOCATION not in {"global", ""}
    else "https://geminidataanalytics.googleapis.com/v1beta",
)


def cymbal_analytics_tool(query: str) -> str:
    """Queries the Cymbal Operations BigQuery analytical store via the Conversational Data Agent.

    Use this tool to answer analytical and reporting questions across:
    - Real-time intraday POS checkout ledger (pos_transactions_gold)
    - Real-time cashier anomaly and promo abuse alerts (pos_anomaly_alerts)
    - Store inventory reconciliation and stockout burn rates (gold_inventory_reconciliation_ledger)
    - Historical customer transaction history (historical_transactional_data)
    - AI-extracted warranty terms and policies (warranty_generic_sections_extracted)
    - Cross-cloud AWS S3 transaction data (silver_pos_transactions)

    Args:
        query: The natural language question to ask the analytical data agent.
               Standardized business terms (e.g., 'Net Transaction Revenue',
               'Total On-Hand Inventory', 'Estimated Cover Hours',
               'Cashier Manual Override Rate') must be passed verbatim.

    Returns:
        A structured string containing the analytical findings, SQL queries executed,
        or error details.
    """
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    auth_req = Request()

    max_retries = 3
    backoff_factor = 2.0
    settings = DataAgentToolConfig()

    for attempt in range(1, max_retries + 1):
        try:
            credentials.refresh(auth_req)
            result = ask_data_agent(
                data_agent_name=DATA_AGENT_NAME,
                query=query,
                credentials=credentials,
                settings=settings,
                tool_context=None,
            )

            if result.get("status") == "SUCCESS":
                response_steps = result.get("response", [])
                final_parts = []
                generated_sql = None
                data_results = None

                for item in response_steps:
                    text_obj = item.get("text", {})
                    if text_obj.get("textType") == "FINAL_RESPONSE":
                        final_parts.extend(text_obj.get("parts", []))

                    data_obj = item.get("data", {})
                    if "matchedQuery" in data_obj:
                        generated_sql = (
                            data_obj["matchedQuery"]
                            .get("exampleQuery", {})
                            .get("sqlQuery")
                        )
                    elif "query" in data_obj and not generated_sql:
                        generated_sql = data_obj["query"].get("generatedSql")

                    if "Data Retrieved" in item:
                        retrieved = item["Data Retrieved"]
                        headers = retrieved.get("headers", [])
                        rows = retrieved.get("rows", [])
                        if headers and rows:
                            data_results = [
                                dict(zip(headers, row, strict=False)) for row in rows
                            ]
                    elif "result" in data_obj:
                        data_results = data_obj["result"].get("data")

                output = []
                if final_parts:
                    output.append(mask_pii_text("\n".join(final_parts)))
                if data_results:
                    output.append(
                        f"\nData Results ({len(data_results)} records):\n"
                        + json.dumps(mask_pii_data(data_results[:20]), indent=2)
                    )
                if generated_sql:
                    output.append(f"\nGenerated SQL Query:\n{generated_sql}")

                if output:
                    return "\n\n".join(output)
                return json.dumps(mask_pii_data(response_steps), indent=2)

        except Exception:
            pass

        if attempt < max_retries:
            time.sleep(backoff_factor**attempt)

    return json.dumps(
        {
            "status": "ERROR",
            "message": "Regional analytical data is temporarily unreachable",
        },
        indent=2,
    )
