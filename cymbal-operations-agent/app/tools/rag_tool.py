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

"""POS Troubleshooting RAG Tool (pos_troubleshooting_rag_tool) querying BigQuery vector embeddings."""

import os
import re
import time
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from google.cloud import bigquery

# Load local .env first to override any stale shell env vars
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"), override=True)

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("PROJECT_ID", ""))
EMBEDDING_TABLE = f"`{PROJECT_ID}.cymbal_gold.pos_manual_chunk_embeddings`"
EMBEDDING_MODEL = f"`{PROJECT_ID}.cymbal_gold.pos_text_embedding_model`"
SIMILARITY_THRESHOLD = 0.70


def _gcs_to_https(uri: str) -> str:
    """Converts a gs:// URI to an HTTPS clickable Google Cloud Storage link."""
    if not uri:
        return uri
    if uri.startswith("gs://"):
        return uri.replace("gs://", "https://storage.cloud.google.com/")
    return uri


def pos_troubleshooting_rag_tool(query: str) -> str:
    """Searches POS terminal technical manuals and SOP runbooks using semantic vector search.

    Use this tool when users ask about POS hardware errors (e.g. ERR-PAY-4001, ERR-TGCS-PWR-90W,
    ERR-DRAWER-STALL, ERR-SCAN-BEAM-03, beep codes, LED fault patterns, thermal shutdown),
    field recovery protocols, hardware troubleshooting SOPs, or maintenance runbooks for POS models
    (e.g., Toshiba TCx 810).

    Args:
        query: The technical error code, hardware issue description, or SOP recovery question.

    Returns:
        The matched SOP recovery protocol, surrounding context, equipment covered, and certified GCS PDF link.
    """
    client = bigquery.Client(project=PROJECT_ID)
    max_retries = 3
    backoff_factor = 2.0

    # Step 0: Extract exact hardware error code tokens for SQL regex boosting
    err_matches = re.findall(r"(ERR-[A-Za-z0-9\-]+|[A-Z]{3,}-\d{3,}|ERR_\w+)", query, re.IGNORECASE)
    exact_error_code = err_matches[0].upper() if err_matches else ""

    # Step 1: Hybrid Vector similarity search with regex error code boosting & adjacent context stitching (N-1 to N+1)
    vector_sql = f"""
    WITH matched AS (
      SELECT 
        base.chunk_index,
        base.document_filename,
        base.document_title,
        base.equipment_covered,
        base.source_pdf_uri,
        base.chunk_content,
        distance,
        CASE 
          WHEN @exact_code != '' AND REGEXP_CONTAINS(UPPER(base.chunk_content), UPPER(@exact_code)) THEN 0.25
          ELSE 0.0
        END AS error_code_boost
      FROM VECTOR_SEARCH(
        TABLE {EMBEDDING_TABLE},
        "embedding",
        (
          SELECT ml_generate_embedding_result AS embedding
          FROM ML.GENERATE_EMBEDDING(
            MODEL {EMBEDDING_MODEL},
            (SELECT @user_query AS content),
            STRUCT("RETRIEVAL_QUERY" AS task_type)
          )
        ),
        top_k => 5,
        distance_type => "COSINE"
      )
    )
    SELECT 
      m.document_filename,
      m.document_title,
      m.equipment_covered,
      m.source_pdf_uri,
      ROUND(LEAST(1.0, (1 - m.distance) + m.error_code_boost), 4) AS similarity_score,
      m.chunk_index,
      STRING_AGG(c.chunk_content, "\\n" ORDER BY c.chunk_index ASC) AS stitched_context
    FROM matched m
    JOIN {EMBEDDING_TABLE} c
      ON m.document_filename = c.document_filename
      AND c.chunk_index BETWEEN (m.chunk_index - 1) AND (m.chunk_index + 1)
    GROUP BY m.document_filename, m.document_title, m.equipment_covered, m.source_pdf_uri, m.distance, m.error_code_boost, m.chunk_index
    ORDER BY similarity_score DESC
    LIMIT 1
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("user_query", "STRING", query),
            bigquery.ScalarQueryParameter("exact_code", "STRING", exact_error_code),
        ]
    )

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            job = client.query(vector_sql, job_config=job_config)
            rows = list(job.result())
            if rows:
                best_row = rows[0]
                similarity_score = float(best_row.similarity_score)

                if similarity_score >= SIMILARITY_THRESHOLD:
                    doc_link = _gcs_to_https(best_row.source_pdf_uri)
                    return (
                        f"### Standard Operating Procedure (SOP) & Troubleshooting Guide\n\n"
                        f"**Document Title:** {best_row.document_title}\n"
                        f"**Equipment Covered:** {best_row.equipment_covered}\n"
                        f"**Relevance Similarity Score:** {similarity_score:.4f}\n"
                        f"**Source Document Link:** [{best_row.document_filename}]({doc_link})\n\n"
                        f"#### Procedural Runbook & Recovery Protocol:\n"
                        f"{best_row.stitched_context}"
                    )
            # If no rows or score below threshold, fall through to Step 2
            break
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                time.sleep(backoff_factor ** attempt)

    # Step 2: Fallback to full-text SEARCH if vector similarity is below threshold or query fails
    tokens = re.findall(r"[A-Za-z0-9]+", query)
    error_tokens = [t for t in tokens if len(t) >= 3 and (any(c.isdigit() for c in t) or t.upper() in {"ERR", "POS", "EMV", "PINPAD", "DRAWER", "SCANNER", "BEAM", "FEED", "CUTTER"})]
    if error_tokens:
        search_term = " ".join(error_tokens[:3])
        fallback_sql = f"""
        WITH text_matches AS (
          SELECT 
            chunk_index,
            document_filename,
            document_title,
            equipment_covered,
            source_pdf_uri
          FROM {EMBEDDING_TABLE}
          WHERE SEARCH(chunk_content, @search_term)
          ORDER BY chunk_index DESC
          LIMIT 1
        )
        SELECT 
          m.document_filename,
          m.document_title,
          m.equipment_covered,
          m.source_pdf_uri,
          STRING_AGG(c.chunk_content, "\\n" ORDER BY c.chunk_index ASC) AS stitched_context
        FROM text_matches m
        JOIN {EMBEDDING_TABLE} c
          ON m.document_filename = c.document_filename
          AND c.chunk_index BETWEEN (m.chunk_index - 1) AND (m.chunk_index + 1)
        GROUP BY m.document_filename, m.document_title, m.equipment_covered, m.source_pdf_uri, m.chunk_index
        LIMIT 1
        """
        fallback_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("search_term", "STRING", search_term)
            ]
        )
        try:
            job = client.query(fallback_sql, job_config=fallback_config)
            f_rows = list(job.result())
            if f_rows:
                f_row = f_rows[0]
                doc_link = _gcs_to_https(f_row.source_pdf_uri)
                return (
                    f"### Standard Operating Procedure (SOP) & Troubleshooting Guide (Keyword Search Fallback)\n\n"
                    f"**Document Title:** {f_row.document_title}\n"
                    f"**Equipment Covered:** {f_row.equipment_covered}\n"
                    f"**Source Document Link:** [{f_row.document_filename}]({doc_link})\n\n"
                    f"#### Procedural Runbook & Recovery Protocol:\n"
                    f"{f_row.stitched_context}"
                )
        except Exception as e:
            last_error = str(e)

    # Step 3: Return exact mandated compliance refusal string when out-of-scope or below threshold
    return "I cannot find certified warranty or repair rules for this specific error in our technical repository."
