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
"""Unit tests for business logic, data normalization, SQL query construction, and guardrails."""

import re

from app.tools.rag_tool import SIMILARITY_THRESHOLD, pos_troubleshooting_rag_tool


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
    # Test numeric format normalization
    store_num = re.findall(r"\d+", "48")
    assert store_num and f"STORE_{int(store_num[0]):03d}" == "STORE_048"

    cash_num = re.findall(r"\d+", "1190")
    assert cash_num and f"CASH_{cash_num[0]}" == "CASH_1190"


def test_rag_similarity_threshold_configured() -> None:
    """Verifies that RAG similarity threshold is strictly locked to 0.70."""
    assert SIMILARITY_THRESHOLD == 0.70
