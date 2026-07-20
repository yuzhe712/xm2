"""Real-LLM E2E test: verify reviewer returns consistent after IntakeAgent prompt fix."""
from __future__ import annotations

import os
import sys

# Must set env vars BEFORE importing config
os.environ["INTAKE_AGENT_STRATEGY"] = "llm"
os.environ["DIAGNOSIS_AGENT_STRATEGY"] = "llm"
os.environ["SUPPORT_REPLY_AGENT_STRATEGY"] = "llm"
os.environ["LLM_PROVIDER"] = "deepseek"
os.environ["LLM_MODEL"] = "deepseek-chat"
os.environ["DEEPSEEK_BASE_URL"] = "https://api.deepseek.com"
os.environ["DEEPSEEK_API_KEY"] = "sk-f53c9326bd754330849c2e16d791f78b"
os.environ["DINGTALK_ENABLED"] = "false"
os.environ["DATA_MODE"] = "mock"
os.environ["MOCK_DATA_DIR"] = "mock_data"

# Set a temp DB to not pollute the real one
os.environ["TICKET_HISTORY_DB_PATH"] = "data/e2e_llm_test.sqlite3"

from fastapi.testclient import TestClient
from intelliticket_backend.main import app


def main() -> int:
    client = TestClient(app)

    # Login as operator
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"user_id": "zhangsan", "password": "zhangsan123"},
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.json()}"
    token = login_resp.json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    text = "线上支付服务出现超时告警，订单量从正常1000/min降到300/min"

    print("=" * 70)
    print("E2E LLM Test: Submitting ticket...")
    print(f"  Text: {text}")
    print("=" * 70)

    resp = client.post(
        "/api/v1/tickets/process",
        json={"text": text, "data_mode": "mock"},
        headers=auth,
    )

    if resp.status_code != 200:
        print(f"\nFAILED with status {resp.status_code}:")
        print(resp.json())
        return 1

    data = resp.json()
    ticket_id = data["ticket_id"]
    run_id = data["run_id"]
    classification = data["classification"]
    review = data.get("review")
    agent_trace = [item["step"] for item in data["agent_trace"]]

    print(f"\n  ticket_id:  {ticket_id}")
    print(f"  run_id:     {run_id}")
    print(f"  agent_trace: {agent_trace}")

    print(f"\n--- Classification ---")
    print(f"  category:         {classification['category']}")
    print(f"  affected_service: {classification['affected_service']}")
    print(f"  priority:         {classification['priority']}")
    print(f"  symptoms:         {classification['symptoms']}")
    print(f"  summary:          {classification['summary']}")

    print(f"\n--- Diagnosis ---")
    diag = data["diagnosis"]
    for i, cause in enumerate(diag.get("candidate_root_causes", []), 1):
        print(f"  Root cause {i}: {cause.get('description', cause.get('hypothesis', ''))[:120]}")
    if diag.get("abstentions"):
        print(f"  Abstentions: {diag['abstentions']}")

    print(f"\n--- Routing ---")
    routing = data["routing"]
    print(f"  recommended_team: {routing['recommended_team']}")
    for i, action in enumerate(routing.get("recommended_actions", []), 1):
        print(f"  Action {i}: {action.get('description', '')[:120]}")

    print(f"\n--- Reviewer ---")
    if review:
        print(f"  status:         {review['review_status']}")
        print(f"  confidence:     {review.get('confidence', 'N/A')}")
        print(f"  recommendation: {review.get('recommendation', 'N/A')[:200]}")
        if review.get("issues"):
            print(f"  Issues ({len(review['issues'])}):")
            for issue in review["issues"]:
                print(f"    [{issue['severity']}] [{issue['category']}] {issue['description'][:150]}")
        else:
            print(f"  Issues: none")
    else:
        print("  (no review field in response)")

    print(f"\n--- Report ---")
    report = data.get("report", {})
    print(f"  recommendations: {len(report.get('recommendations', []))} recommendations")

    print("\n" + "=" * 70)

    # Check: reviewer should be consistent (not flagged due to service name mismatch)
    if review:
        status = review["review_status"]
        if status == "consistent":
            print("✅ PASS: Reviewer returned 'consistent' — service name fix works!")
            return 0
        elif status == "flagged":
            print("⚠️  REVIEWER FLAGGED — issues:")
            for issue in review.get("issues", []):
                print(f"    [{issue['severity']}] [{issue['category']}] {issue['description'][:200]}")
            return 1
        elif status == "abstain":
            print("⚠️  REVIEWER ABSTAINED — LLM may have failed or returned uncertain")
            return 1
        else:
            print(f"⚠️  Unexpected review_status: {status}")
            return 1
    else:
        print("⚠️  No review field in response — reviewer may not be running")
        return 1


if __name__ == "__main__":
    sys.exit(main())
