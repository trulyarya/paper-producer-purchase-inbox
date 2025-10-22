# Agent Prompts Directory

This folder stores the production prompts that power the O2C multi-agent workflow. Each file documents the exact behavior expected from its agent and reflects the latest architecture.

## Prompt Index

### `email_triage_agent.md`
Classifies a single email as a purchase order or not. Provides a lightweight decision framework, confidence ladder, and succinct JSON response format (`is_po`, `confidence`, `reason`).

### `po_parser_agent.md`
Extracts structured data from confirmed purchase orders. Includes a checklist for metadata, customer info, the new `line_reference` field, and guidance on preserving raw descriptions.

### `sku_resolver_agent.md`
Selects the best SKU from orchestrator-supplied candidate lists. Explains the `SkuResolutionPayload` input, confidence thresholds, and the enriched output schema with `needs_review` flags.

### `comms_exceptions_agent.md`
Currently on standby. Captures the future requirements for a dedicated communications/exception agent so the team can activate it later without rediscovering the rules.

### `orchestrator_agent.md`
The playbook for the top-level agent. Describes the new `prepare_sku_candidates` step, sequencing rules for deterministic tools, and the final reporting template.

## Design Principles
1. **Clarity first** – Plain-language steps with minimal fluff.
2. **Token aware** – Examples are focused; unnecessary prose is removed.
3. **Traceability** – Agents log decisions, confidence, and review flags.
4. **Extensibility** – Prompts reference shared Pydantic schemas so updates stay consistent with code.

## Loading Prompts
Prompts are loaded at runtime from this directory:
```python
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent

def load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")
```

## Maintenance Checklist
- Update prompts whenever business rules or schemas change.
- Keep change history in git for easy rollback.
- Test prompt adjustments against the sample inbox before deploying.

_Last updated: 2024-10-23_
