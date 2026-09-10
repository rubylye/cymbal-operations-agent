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

"""PII and Payment Card Number (PCI-DSS) Redaction and Masking Utility."""

import re
from typing import Any

# Regex patterns for Credit/Debit Cards (Visa, MasterCard, Amex, Discover: 13-19 digits formatted or raw)
CARD_PATTERN = re.compile(
    r"\b(?:"
    r"(?:\d{4}[-\s]?){3}\d{4}"  # 16-digit cards with optional hyphens/spaces
    r"|\d{4}[-\s]?\d{6}[-\s]?\d{5}"  # 15-digit Amex cards
    r"|\d{13,19}"  # 13 to 19 contiguous card digits
    r")\b"
)


def mask_credit_card(card_match: str) -> str:
    """Masks a detected credit card number into standard XXXX-XXXX-XXXX-9999 format."""
    digits_only = re.sub(r"\D", "", card_match)
    if len(digits_only) < 13 or len(digits_only) > 19:
        return card_match
    last4 = digits_only[-4:]
    return f"XXXX-XXXX-XXXX-{last4}"


def mask_pii_text(text: str) -> str:
    """Detects and redacts payment card numbers (PCI-DSS PII) from text payloads."""
    if not text or not isinstance(text, str):
        return text

    def _repl(match: re.Match[str]) -> str:
        matched_str = match.group(0)
        digits = re.sub(r"\D", "", matched_str)
        # Avoid masking simple dates or short numbers
        if len(digits) >= 13 and len(digits) <= 19:
            return mask_credit_card(matched_str)
        return matched_str

    return CARD_PATTERN.sub(_repl, text)


def mask_pii_data(data: Any) -> Any:
    """Recursively masks PII in nested JSON dicts, lists, or string structures."""
    if isinstance(data, str):
        return mask_pii_text(data)
    elif isinstance(data, dict):
        return {k: mask_pii_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [mask_pii_data(elem) for elem in data]
    return data
