"""Test update_customer_credit function in isolation"""
import sys
from pathlib import Path

# Add src to path
PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(PROJECT_SRC))

from crm.airtable_tools import update_customer_credit

def test_update_customer_credit():
    """Test the update_customer_credit function with real parameters from the failed workflow"""
    try:
        result = update_customer_credit(
            customer_id="C-5002",
            order_amount=440.65
        )
        print(f"Success! Result: {result}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_update_customer_credit()
