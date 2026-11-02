"""
FILE:         src/prompt_engine/templating.py
WHAT IT DOES: Builds the one Jinja2 environment every human-turn template is rendered with.
WHERE IT FITS: Defines the custom filters templates may use (xml_safe). The composer (Phase 3)
              renders with it; tests parse templates with it.
"""

from xml.sax.saxutils import escape as escape_xml

from jinja2 import BaseLoader, Environment, StrictUndefined


# --- 1. The xml_safe filter: neutralises <, > and & in customer data -----------------------------
# A ticket body containing "</ticket><role>..." renders as "&lt;/ticket&gt;&lt;role&gt;...",
# so customer text can never close or open a prompt boundary tag.
def xml_safe(value: object) -> str:
    return escape_xml(str(value))


# --- 2. Environment settings -------------------------------------------------------------------
# StrictUndefined          → a missing variable is an error, never a silent empty string
# autoescape=False         → we escape explicitly with | xml_safe (HTML rules are the wrong fit)
# trim_blocks/lstrip_blocks → {# comments #} and {% tags %} leave no stray blank lines
def build_template_environment() -> Environment:
    template_environment = Environment(
        loader=BaseLoader(),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
    )
    template_environment.filters["xml_safe"] = xml_safe
    return template_environment
