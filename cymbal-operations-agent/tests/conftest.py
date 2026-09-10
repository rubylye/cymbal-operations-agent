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

"""Test configuration and dynamic credential setup for test execution in offline/sandboxed environments."""

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def setup_test_environment() -> None:
    """Configures dynamic GCP Vertex AI / Gemini API keys and test targets for sandbox test runs."""
    # Ensure offline/sandboxed test runners have valid fallback credentials/mode
    if not os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_GENAI_USE_VERTEXAI"):
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"

    if not os.getenv("GOOGLE_CLOUD_LOCATION"):
        os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        os.environ["GOOGLE_CLOUD_PROJECT"] = os.getenv(
            "PROJECT_ID", "data-advanced-ruby"
        )

    if not os.getenv("BIGTABLE_INSTANCE"):
        os.environ["BIGTABLE_INSTANCE"] = "operations-db"

    if not os.getenv("BIGTABLE_MCP_URL"):
        os.environ["BIGTABLE_MCP_URL"] = (
            "https://mcp-toolbox-bigtable-766762791496.us-central1.run.app"
        )
