from dotenv import load_dotenv

from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.observability import setup_observability
from azure.identity import AzureCliCredential

# Ensure environment and telemetry are configured before agents initialize.
load_dotenv()
setup_observability()

# Shared chat client instance used by all agents.
chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())
