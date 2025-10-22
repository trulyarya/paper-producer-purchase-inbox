import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    FunctionTool,  # define custom functions
    ToolSet,  # group multiple tools
    AgentsResponseFormat,  # define response format
    ResponseFormatJsonSchema,  # define response format schema
    ResponseFormatJsonSchemaType,  # specify response format type
    ConnectedAgentTool,  # define connected agent tools. This is a tool that can call other agents, in order to chain agents together.
)
from src.email.gmail_grabber import authenticate_gmail, fetch_unread_emails  # Import Gmail functions
from src.shared.po_schema import PurchaseOrder  # Import the Pydantic schema for structured purchase orders

# Load environment variables from .env file
load_dotenv()
project_endpoint = os.getenv("AZURE_AI_FOUNDRY_PROJECT_ENDPOINT")
model_deployment = os.getenv("AZURE_TRIAGE_MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini")  # use smaller model by default for faster triage
po_model_deployment = os.getenv(
    "AZURE_PO_MODEL_DEPLOYMENT_NAME",
    os.getenv("AZURE_MODEL_DEPLOYMENT_NAME", model_deployment),
)  # fall back to triage model if no dedicated PO model is configured

# Connect to the Agent client
agent_client = AgentsClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential()
)


# Define tool wrapper the agent can call without extra arguments
def gmail_grabber():
    """Fetch unread Gmail messages and return structured email details."""
    service = authenticate_gmail()
    return fetch_unread_emails(service)


# Define an agent that can use the custom functions
with agent_client:

    po_response_format = ResponseFormatJsonSchemaType(
        json_schema=ResponseFormatJsonSchema(
            name="PurchaseOrderExtraction",
            description="Structured purchase order data extracted from a single email payload.",
            schema=PurchaseOrder.model_json_schema(ref_template="#/components/schemas/{model}"),
        )
    )

    gmail_purchase_order_agent = agent_client.create_agent(
        model=po_model_deployment,
        name="gmail-purchase-order-parser-agent",
        instructions="""
You are a subordinate purchase order parsing agent. The triage agent will call you with a JSON object describing a SINGLE email that has already been classified as a purchase order.

Input format example:
{
  "id": "...",
  "sender": "...",
  "subject": "...",
  "snippet": "...",
  "body": "..."
}

Use every detail available to populate the purchase order schema. If specific data is not present, return null for that field but keep the schema valid. Always include at least one order line by synthesizing from the email description when necessary.
""",
        response_format=po_response_format,
    )

    po_parser_tool = ConnectedAgentTool(
        id=gmail_purchase_order_agent.id,
        name="parse_purchase_order_email",
        description="Parses a purchase order email JSON payload into structured data.",
    )

    functions = FunctionTool({gmail_grabber})
    toolset = ToolSet()
    toolset.add(functions)
    toolset.add(po_parser_tool)
    agent_client.enable_auto_function_calls(toolset)

    # Note: response_format with json_schema is not supported by all model versions
    # Instead, we'll rely on clear instructions to get JSON output
    
    # Create the agent, enabling connected tools
    agent = agent_client.create_agent(
        model=model_deployment,
        name="gmail-purchase-order-triage-agent",
        instructions=
        """You are an email triage agent. Your sole purpose is to determine if an incoming email is a Purchase Order (PO) or not.
        
        Workflow:
        1. Call gmail_grabber once to fetch unread emails. You will receive a JSON array where each entry has id, sender, subject, snippet, and body.
        2. Analyze each email independently to decide if it is a purchase order.
        3. Whenever you determine is_po is true, immediately call the parse_purchase_order_email tool. Pass the entire email JSON (id, sender, subject, snippet, body) as the tool input. Wait for its response before finalizing your answer and include the returned JSON under the po_details field for that email.
        4. If an email is not a PO, set po_details to null.
        
        Consider it a PO if it contains:
        - Purchase order numbers or references
        - Line items with quantities and prices
        - Buyer/vendor information
        - Delivery or shipping details
        - Total amounts
        - Any formal ordering language
        - Specific formatting typical of purchase orders
        - Clear intent to place an order for goods or services
        - etc.

        Output format:
        Important: Respond with a valid JSON array where each element represents one email with this exact structure:
        {
          "sender": "the email address of the sender",
          "subject": "the email subject",
          "is_po": true or false,
          "confidence": 0.0 to 1.0,
          "reason": "brief explanation for your decision",
          "body": "the email body text",
          "po_details": { ... } OR null  // include the connected agent response when is_po is true
        }
        
        Example output:
        [
          {
            "sender": "sender@example.com",
            "subject": "PO #1234 - Office Supplies",
            "is_po": true,
            "confidence": 0.95,
            "reason": "Contains PO number, line items with quantities and prices",
            "body": "Full email body text here...",
            "po_details": {
              "po_number": "1234",
              "order_date": "2024-02-01",
              "requested_ship_date": null,
              "customer": {
                "customer_name": "Acme Corp",
                "contact_person": "Jane Doe",
                "email": "jane.doe@acme.com"
              },
              "order_lines": [
                {
                  "product_code": "PAPER-A4-100-COATEDGLOSS-M",
                  "product_description": "Premium A4 Gloss Paper - 100gsm",
                  "quantity": 25,
                  "unit": "case",
                  "unit_price": 45.5,
                  "line_total": 1137.5
                }
              ],
              "net_amount": 1137.5,
              "gmail_message_id": "18c8fdd2e34aa19c",
              "notes": null
            }
          },
            {
                "sender": "sender@example.com",
                "subject": "PO #5678 - Office Supplies",
                "is_po": true,
                "confidence": 0.90,
                "reason": "Contains PO number, line items with quantities and prices",
                "body": "Full email body text here...",
                "po_details": { "po_number": "5678", "...": "..." }
            }
        ]
        """,
        toolset=toolset,
        response_format=AgentsResponseFormat(type="json_object"),
    )

    # Create a new thread for the agent interaction
    thread = agent_client.threads.create()

    # Initial user message to start the agent process
    agent_client.messages.create(
        thread_id=thread.id,
        role="user",
        content=
        """Fetch unread Gmail messages, detect whether they are purchase orders.
Respond using the strictly defined JSON schema, and include po_details populated via the parse_purchase_order_email tool for every PO.
        
# Output

A JSON object PER EMAIL indicating if it is a purchase order or not, with confidence, reason, email body, and po_details (null when not a PO).
""",
    )

    # Run agent and get response.
    run = agent_client.runs.create_and_process(
        thread_id=thread.id,
        agent_id=agent.id,
        toolset=toolset,
    )

    messages = agent_client.messages.list(thread_id=thread.id)
    
    print("----------- Agent Response:-----------\n\n")
    for message in messages:
        print(f"{message.role.upper()}:")
        for block in message.content:
            if getattr(block, "type", None) == "text":
                print(block.text)
            else:
                print(block)
        print()
