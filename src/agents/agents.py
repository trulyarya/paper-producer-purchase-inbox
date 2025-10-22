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
    AgentsNamedToolChoice,  # specify tool usage
    AgentsNamedToolChoiceType,  # specify tool choice type
    FunctionName,  # specify function names that will be used
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
    
    response_format = ResponseFormatJsonSchemaType(
        json_schema=ResponseFormatJsonSchema(
            name="POExtraction",
            description="Structured purchase-order data from unread Gmail messages.",
            schema=PurchaseOrder.model_json_schema(ref_template="#/components/schemas/{model}"),
        )
    )

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

    thread = agent_client.threads.create()
    
    # Run agent and get response
    run = agent_client.runs.create_and_process(
        thread_id=thread.id,
        agent_id=agent.id,
        tool_choice=AgentsNamedToolChoice(
            type=AgentsNamedToolChoiceType.FUNCTION,
            function=FunctionName(name="gmail_grabber"),
        ),
    )

    message = agent_client.messages.list(thread_id=thread.id)#[-1]
    print("----------- Agent Response:-----------\n\n", message.content)
