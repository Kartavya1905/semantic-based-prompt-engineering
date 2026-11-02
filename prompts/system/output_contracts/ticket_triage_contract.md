Category definitions (choose the single dominant issue):
- billing: charges, invoices, refunds, payment methods, plan prices.
- technical: errors, outages, bugs, slowness, integrations, API behaviour, and how-to questions
  about using the product.
- account: sign-in, passwords, permissions, user management, account deletion.
- feature_request: asks for a capability the product does not have yet.
- other: nothing above fits. Prefer a specific category whenever one reasonably applies.

Field guidance:
- summary: one third-person sentence. Include concrete identifiers. Do not guess at causes.
- extracted_entities: copy identifiers exactly as written in the ticket. Use product only when the
  ticket names a product. Use an empty list when there are none. Never invent an identifier.
- confidence_score: your probability that category AND urgency are both correct. Use a value
  below 0.6 when the ticket is vague or mixes several issues.

Format:
- Reply with one JSON object that matches <output_schema>.
- No Markdown code fences, and no text before or after the JSON.
