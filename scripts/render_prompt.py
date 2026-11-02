"""
FILE:         scripts/render_prompt.py
WHAT IT DOES: Prints the exact messages a prompt variant would send to the model, without
              calling any model. Use it to read, review and compare variants.
USE:          python scripts/render_prompt.py ticket_triage v1_baseline
              python scripts/render_prompt.py ticket_triage v3_fewshot --ticket my_ticket.json
              python scripts/render_prompt.py ticket_triage --list
"""

import argparse
import json
import sys
from pathlib import Path

from prompt_engine.composer import PromptComposer
from prompt_engine.registry import PromptRegistry

# --- 1. A sample ticket used when --ticket is not given ---
SAMPLE_TICKET = {
    "customer_tier": "enterprise",
    "ticket_subject": "URGENT: production API returning 500",
    "ticket_body": "Since 09:14 UTC every call to /v2/orders fails with E-5012.",
}


def main() -> int:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("prompt_id")
    argument_parser.add_argument("variant_label", nargs="?")
    argument_parser.add_argument("--ticket", type=Path, help="JSON file of template variables")
    argument_parser.add_argument("--list", action="store_true", help="list variants and exit")
    parsed_args = argument_parser.parse_args()
    registry = PromptRegistry()

    # --- 2. --list: show the variants that exist ---
    if parsed_args.list or parsed_args.variant_label is None:
        for variant_label in registry.list_variants(parsed_args.prompt_id):
            print(variant_label)
        return 0

    # --- 3. Compose and print both messages with a short header ---
    ticket_variables = (
        json.loads(parsed_args.ticket.read_text(encoding="utf-8"))
        if parsed_args.ticket
        else SAMPLE_TICKET
    )
    manifest = registry.load_manifest(parsed_args.prompt_id, parsed_args.variant_label)
    composed_prompt = PromptComposer(registry).compose(manifest, ticket_variables)
    total_characters = len(composed_prompt.system_message) + len(composed_prompt.human_message)

    print(f"# {composed_prompt.prompt_id}/{parsed_args.variant_label} "
          f"v{composed_prompt.manifest_version}  fingerprint={composed_prompt.prompt_fingerprint}")
    print(f"# {total_characters} characters (~{total_characters // 4} tokens), "
          f"generation={composed_prompt.generation_params.model_dump()}")
    print("\n=================== SYSTEM ===================")
    print(composed_prompt.system_message)
    print("\n==================== USER ====================")
    print(composed_prompt.human_message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
