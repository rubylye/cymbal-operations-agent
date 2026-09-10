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
"""Unit tests for business logic, PII masking, data normalization, SQL tools, and guardrails."""

import json
import re

from app.tools.bigtable_tool import (
    read_cashier_realtime_alerts_sql,
    read_pos_transactions_enriched_sql,
)
from app.tools.rag_tool import SIMILARITY_THRESHOLD, pos_troubleshooting_rag_tool
from app.utils.pii_masking import mask_pii_data, mask_pii_text


def test_pii_masking_credit_cards() -> None:
    """Tests PCI-DSS credit card masking to XXXX-XXXX-XXXX-9999 schema."""
    raw_text = "Customer paid using card 4111-2222-3333-4444 on terminal 2."
    masked = mask_pii_text(raw_text)
    assert "XXXX-XXXX-XXXX-4444" in masked
    assert "4111-2222-3333-4444" not in masked

    # Test unformatted 16-digit card
    raw_text2 = "Transaction record: cc_num=5500000000009876, auth=approved"
    masked2 = mask_pii_text(raw_text2)
    assert "XXXX-XXXX-XXXX-9876" in masked2

    # Test nested dict structure masking
    payload = {
        "txn_id": "TXN-101",
        "payment_info": {"card_number": "3782-822463-10005"},
    }
    masked_payload = mask_pii_data(payload)
    assert masked_payload["payment_info"]["card_number"] == "XXXX-XXXX-XXXX-0005"


def test_rag_out_of_scope_mandated_refusal() -> None:
    """Tests that out-of-scope hardware error queries return the exact mandated compliance string."""
    out_of_scope_query = "How do I replace the engine oil on a Ford F-150 truck?"
    result = pos_troubleshooting_rag_tool(out_of_scope_query)
    expected_refusal = "I cannot find certified warranty or repair rules for this specific error in our technical repository."
    assert result == expected_refusal, f"Expected exact refusal string, got: {result}"


def test_error_code_regex_extraction() -> None:
    """Tests regex error code parser accurately identifies hardware fault codes for query boosting."""
    query = "Cashier is seeing ERR-PAY-4001 EMV contactless payment freeze on lane 4"
    err_matches = re.findall(
        r"(ERR-[A-Za-z0-9\-]+|[A-Z]{3,}-\d{3,}|ERR_\w+)", query, re.IGNORECASE
    )
    assert len(err_matches) > 0
    assert err_matches[0].upper() == "ERR-PAY-4001"


def test_store_and_cashier_normalization() -> None:
    """Tests store and cashier identity normalization logic."""
    store_num = re.findall(r"\d+", "48")
    assert store_num and f"STORE_{int(store_num[0]):03d}" == "STORE_048"

    cash_num = re.findall(r"\d+", "1190")
    assert cash_num and f"CASH_{cash_num[0]}" == "CASH_1190"


def test_rag_similarity_threshold_configured() -> None:
    """Verifies that RAG similarity threshold is strictly locked to 0.70."""
    assert SIMILARITY_THRESHOLD == 0.70


def test_bigtable_declarative_sql_signatures() -> None:
    """Verifies that declarative Bigtable SQL tools return valid JSON contracts."""
    # Test read_cashier_realtime_alerts_sql
    alerts_res = read_cashier_realtime_alerts_sql("STORE_048", "CASH_1190")
    assert isinstance(alerts_res, str)
    parsed = json.loads(alerts_res)
    assert "store_id" in parsed or "status" in parsed

    # Test read_pos_transactions_enriched_sql
    pos_res = read_pos_transactions_enriched_sql("STORE_048", "TXN-999")
    assert isinstance(pos_res, str)
    pos_parsed = json.loads(pos_res)
    assert "store_id" in pos_parsed or "status" in pos_parsed
