"""Command-line entry point for the PaperCo PO intake workflow."""

import asyncio


from src.workflow.workflow import (
    run_till_mail_read,  # Import the async function to run the workflow
    workflow,
)

def main() -> None:
    """Start the asynchronous Gmail polling loop."""
    
    # # UNCOMMENT BELOW to run the workflow:

    # Run the workflow to process unread emails
    asyncio.run(run_till_mail_read())


    # # UNCOMMENT BELOW TWO LINES to start the DevUI to visualize the workflow:

    # from agent_framework_devui import serve  # serve means to start the dev UI
    # serve([workflow], auto_open=True)  # Automatically open the UI in a browser


if __name__ == "__main__":
    main()