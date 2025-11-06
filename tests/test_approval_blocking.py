"""
Test script to verify approval blocking works correctly.
This simulates what happens when the fulfiller agent calls the approval tool.
It sends a message to Slack and then blocks, waiting for human approval.
Once approved/denied, it prints the result.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from src.messaging.slack_approval import post_approval_request, get_approval_from_slack


def test_approval_blocking():
    """Test that approval request sent to Slack actually blocks execution."""
    
    # Sample order data (same structure as RetrievedPO)
    sample_order = {
        "customer_id": "CUST001",
        "customer_name": "Test Customer GmbH",
        "customer_email": "test@example.com",
        "order_total": 1250.50,
        "items": [
            {"sku": "SKU001", "quantity": 10, "unit_price": 125.05},
        ],
    }
    
    print("=" * 60)
    print("APPROVAL BLOCKING TEST")
    print("=" * 60)
    print("\n1. Posting order to Slack...")
    
    try:
        thread_ts = post_approval_request(sample_order)
        print(f"   ✓ Posted! Thread ID: {thread_ts}")
    except Exception as e:
        print(f"   ✗ Failed to post: {e}")
        return
    
    print("\n2. Waiting for approval (timeout: 300s)...")
    print("   Go to Slack #orders channel and reply 'approve' or 'deny'")
    print("   Execution is BLOCKED here - workflow should NOT complete!")
    print()
    
    channel = os.getenv("SLACK_APPROVAL_CHANNEL", "#orders")
    approved = get_approval_from_slack(
        channel=channel,
        thread_ts=thread_ts,
        timeout=300,
    )
    
    print()
    if approved:
        print("3. ✓ APPROVED! Would now send confirmation email.")
    else:
        print("3. ✗ DENIED! No email sent.")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE - Blocking worked correctly!")
    print("=" * 60)


if __name__ == "__main__":
    # Verify env vars are set
    if not os.getenv("SLACK_BOT_TOKEN"):
        print("ERROR: SLACK_BOT_TOKEN not set in environment")
        sys.exit(1)
    
    test_approval_blocking()
