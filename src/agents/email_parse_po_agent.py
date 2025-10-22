import os
from dotenv import load_dotenv
from pathlib import Path
from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    FunctionTool,  # define custom functions
    ToolSet,  # group multiple tools
    ResponseFormatJsonSchema,  # define response format schema
    ResponseFormatJsonSchemaType,  # specify response format type
    ConnectedAgentTool,  # define connected agent tools. This is a tool that can call other agents, in order to chain agents together.
)
from src.email.gmail_grabber import authenticate_gmail, fetch_unread_emails  # Import Gmail functions
from src.shared.po_schema import PurchaseOrder  # Import the Pydantic schema for purchase order extraction

# Load environment variables from .env file
load_dotenv()
project_endpoint = os.getenv("AZURE_AI_FOUNDRY_PROJECT_ENDPOINT")
model_deployment = os.getenv("AZURE_MODEL_DEPLOYMENT_NAME")

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

    functions = FunctionTool({gmail_grabber})
    toolset = ToolSet()
    toolset.add(functions)
    agent_client.enable_auto_function_calls(toolset)
    
    # Define the response format using the PurchaseOrder schema
    response_format = ResponseFormatJsonSchemaType(
        json_schema=ResponseFormatJsonSchema(
            name="PurchaseOrderExtraction",
            description="Structured purchase-order data from unread Gmail messages.",
            schema=PurchaseOrder.model_json_schema(ref_template="#/components/schemas/{model}"),
        )
    )
    
    # Create the agent, enabling connected tools
    agent = agent_client.create_agent(
        model=model_deployment,
        name="gmail-purchase-order-agent",
        instructions=
        """You are a Gmail purchase order processing agent. Always call gmail_grabber first to fetch unread emails before analysis.
        Your task is to fetch and analyze unread emails from Gmail to identify purchase orders.
        Use the gmail_grabber function to retrieve unread emails with their subject, sender, and snippet first.
        If they're a PO from a buyer, then carefully examine the body content.
        After that, extract relevant purchase order information from the email bodies and organize the data into JSON output.
        """,
        toolset=toolset,
        response_format=response_format,
    )

    # Create a new thread for the agent interaction
    thread = agent_client.threads.create()

    # Initial user message to start the agent process
    agent_client.messages.create(
        thread_id=thread.id,
        role="user",
        content="Fetch unread Gmail messages, detect purchase orders, and respond with structured PO data.",
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
            print(message.content)

    # thread_messages = list(agent_client.messages.list(thread_id=thread.id))
    # if not thread_messages:
    #     print("No messages were recorded on this thread.")
    # else:
    #     print("----------- Agent Messages -----------")
    #     for message in thread_messages:
    #         role = message.get("role", "unknown").upper()
    #         print(f"{role}:")
    #         content = message.get("content", [])
    #         if isinstance(content, str):
    #             print(content)
    #         else:
    #             for block in content:
    #                 block_type = block.get("type")
    #                 if block_type == "text":
    #                     print(block.get("text", ""))
    #                 else:
    #                     print(f"[{block_type}] {block}")
    #         print()