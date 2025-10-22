"""
SKU Candidate Builder.

This module will eventually handle embedding generation and Azure AI Search
queries so the orchestrator can present a short list of catalog matches to the
SKU resolver agent. For now we only provide the scaffolding.
"""

def build_candidates(payload: dict[str, any], limit: int = 5) -> dict[str, any]:
    """
    Prepare candidate SKUs for each order line contained in `payload`.

    Expected responsibilities (not yet implemented):
      1. Extract order lines from the parsed purchase order.
      2. Generate text embeddings for each description.
      3. Query the vector index and retrieve top `limit` matches per line.
      4. Hydrate each match with CRM metadata (price, unit of measure, stock).
      5. Return a structure the SKU agent can review.
    """
    raise NotImplementedError("Vector search pipeline not implemented yet.")


def _extract_order_lines(payload: dict[str, any]) -> list[dict[str, any]]:
    """Pull order lines out of the purchase order payload."""
    raise NotImplementedError


def _encode_descriptions(order_lines: list[dict[str, any]]) -> list[dict[str, any]]:
    """Generate embeddings for the order line descriptions."""
    raise NotImplementedError


def _query_vector_index(encoded_lines: list[dict[str, any]], limit: int) -> list[list[dict[str, any]]]:
    """Query Azure AI Search for each encoded line and collect top matches."""
    raise NotImplementedError


def _hydrate_with_crm(matches: list[list[dict[str, any]]]) -> list[list[dict[str, any]]]:
    """Attach CRM pricing, UOM, and availability data to each search match."""
    raise NotImplementedError


def _bundle_response(order_lines: list[dict[str, any]], candidates: list[list[dict[str, any]]]) -> dict[str, any]:
    """Combine original lines and candidate lists into the structure expected by the SKU agent."""
    raise NotImplementedError
