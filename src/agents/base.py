import shutil
from dotenv import load_dotenv

from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.observability import setup_observability
from azure.identity import AzureCliCredential, DefaultAzureCredential

# Ensure environment and telemetry are configured before agents initialize.
load_dotenv()
setup_observability()


def _build_chat_client() -> AzureOpenAIChatClient:
    """Create a chat client using the best available authentication."""

    # Prefer non-CLI credentials to keep containers self-contained.
    try:
        return AzureOpenAIChatClient(
            credential=DefaultAzureCredential(exclude_cli_credential=True)
        )
    except Exception:
        pass

    if shutil.which("az"):
        return AzureOpenAIChatClient(credential=AzureCliCredential())

    raise RuntimeError(
        "Azure authentication not configured. Set AZURE_OPENAI_API_KEY or install "
        "Azure CLI inside the container and run `az login`."
    )


# Shared chat client instance used by all agents.
chat_client = _build_chat_client()
