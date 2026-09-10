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
from typing import Any, Dict
import google.auth
from google.auth.transport.requests import Request
import requests

DATA_AGENT_NAME = os.getenv(
    "BIGQUERY_DATA_AGENT_NAME",
    "projects/766762791496/locations/global/dataAgents/agent_ff7cb51a-288b-4141-8f0a-de587aad8a05",
)
BASE_URL = os.getenv(
    "GDA_BASE_URL",
    "https://geminidataanalytics.googleapis.com/v1beta",
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

    parent = DATA_AGENT_NAME.rsplit("/", 2)[0]
    chat_url = f"{BASE_URL}/{parent}:chat"

    payload = {
        "messages": [{"userMessage": {"text": query}}],
        "dataAgentContext": {
            "dataAgent": DATA_AGENT_NAME,
        },
        "clientIdEnum": "GOOGLE_ADK",
    }

    max_retries = 3
    backoff_factor = 2.0
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            credentials.refresh(auth_req)
            headers = {
                "Authorization": f"Bearer {credentials.token}",
                "Content-Type": "application/json",
            }
            resp = requests.post(chat_url, headers=headers, json=payload, timeout=90)
            if resp.status_code == 200:
                response_json = resp.json()
                final_parts = []
                generated_sql = None
                data_results = None

                for item in response_json:
                    sys_msg = item.get("systemMessage", {})
                    text_obj = sys_msg.get("text", {})
                    if text_obj.get("textType") == "FINAL_RESPONSE":
                        final_parts.extend(text_obj.get("parts", []))

                    data_obj = sys_msg.get("data", {})
                    if "matchedQuery" in data_obj:
                        generated_sql = data_obj["matchedQuery"].get("exampleQuery", {}).get("sqlQuery")
                    elif "query" in data_obj and not generated_sql:
                        generated_sql = data_obj["query"].get("generatedSql")

                    if "result" in data_obj:
                        data_results = data_obj["result"].get("data")

                output = []
                if final_parts:
                    output.append("\n".join(final_parts))
                if data_results:
                    output.append(f"\nData Results ({len(data_results)} records):\n" + json.dumps(data_results[:20], indent=2))
                if generated_sql:
                    output.append(f"\nGenerated SQL Query:\n{generated_sql}")

                if output:
                    return "\n\n".join(output)
                return json.dumps(response_json, indent=2)

            last_error = f"HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            last_error = str(e)

        if attempt < max_retries:
            time.sleep(backoff_factor ** attempt)

    return f"Store analytical data is temporarily unreachable. Error details: {last_error}"
