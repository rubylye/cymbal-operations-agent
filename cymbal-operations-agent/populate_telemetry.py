#!/usr/bin/env python3
# Copyright 2026 Google LLC
"""Batch runner script to generate rich telemetry events in BigQuery for cymbal_operations_agent."""

import asyncio
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv(override=True)

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from app.agent import app

PROMPTS = [
    # Session 1: Store Lead Alice (Store 48) - RAG Troubleshooting & Hardware
    {
        "user_id": "alice_store48",
        "session_id": "session_alice_001",
        "prompts": [
            "What is the immediate field recovery protocol when a cashier encounters an ERR-PAY-4001 EMV contactless payment freeze, and how do we ensure the customer is not double-charged?",
            "Cash drawer 2 is completely jammed and reporting error ERR-DRAWER-STALL on Toshiba TCx 810. How should the cashier resolve this immediately?",
            "How do I replace the engine oil on a Ford F-150 truck?",
        ]
    },
    # Session 2: Loss Prevention Bob - Real-time Bigtable & Parallel Baseline Dispatches
    {
        "user_id": "bob_audit_lead",
        "session_id": "session_bob_002",
        "prompts": [
            "Read live 1-hour rolling metrics and audit status flags for Cashier CASH_1190 at Store 48.",
            "What is Cashier CASH_1190's live 1-hour override rate right now, compared to their 7-day historical override baseline?",
            "Retrieve recent sub-second POS checkout transactions for Store 48.",
        ]
    },
    # Session 3: Regional Manager Carol - BigQuery Analytical Store NL2SQL
    {
        "user_id": "carol_regional_mgr",
        "session_id": "session_carol_003",
        "prompts": [
            "What is the estimated cover hours remaining for store inventory positions experiencing stockout risk of less than 20 hours, and what is their total on-hand inventory?",
            "What is the Net Transaction Revenue for Store 8 today?",
            "Show cashiers with active cashier promo abuse alerts in the last 7 days and retrieve checkout logs for the top offender.",
        ]
    },
    # Session 4: Support Engineer Dave - Multi-turn Incident & Optical Diagnostics
    {
        "user_id": "dave_support_eng",
        "session_id": "session_dave_004",
        "prompts": [
            "Barcode scanner beam at checkout register 4 is failing with code ERR-SCAN-BEAM-03. What is the runbook fix?",
            "What is the warranty and return policy for open-box consumer electronics under 30 days?",
            "Check live cashier metrics for Cashier CASH_2042 at Store 12.",
        ]
    }
]

async def run_prompts():
    print("Initializing ADK Session Service and Runner...")
    session_service = InMemorySessionService()
    runner = Runner(app=app, session_service=session_service)

    total_prompts = sum(len(s["prompts"]) for s in PROMPTS)
    count = 0

    for s in PROMPTS:
        user_id = s["user_id"]
        session_id = s["session_id"]
        print(f"\n==========================================")
        print(f"Starting Session: {session_id} (User: {user_id})")
        print(f"==========================================")
        
        session = await session_service.create_session(
            app_name=app.name,
            user_id=user_id,
            session_id=session_id
        )

        for prompt_text in s["prompts"]:
            count += 1
            print(f"\n[{count}/{total_prompts}] User: {prompt_text}")
            msg = types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt_text)]
            )
            
            start_time = time.time()
            events_count = 0
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session.id,
                new_message=msg
            ):
                events_count += 1
                if hasattr(event, "content") and event.content:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            snippet = part.text[:120].replace('\n', ' ')
                            print(f"  -> Agent response snippet: {snippet}...")
                        elif hasattr(part, "function_call") and part.function_call:
                            print(f"  -> Tool Call: {part.function_call.name}")
                        elif hasattr(part, "function_response") and part.function_response:
                            print(f"  -> Tool Response: {part.function_response.name}")

            elapsed = time.time() - start_time
            print(f"  -> Completed turn in {elapsed:.2f}s ({events_count} events generated)")
            await asyncio.sleep(1)

    print("\nAll sessions and prompts completed! Allowing 5s for BigQuery Storage Write API to flush buffer...")
    await asyncio.sleep(5)
    print("Telemetry generation complete.")

if __name__ == "__main__":
    asyncio.run(run_prompts())
