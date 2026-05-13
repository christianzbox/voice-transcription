from __future__ import annotations

DEFAULT_TEMPLATE = "meeting"

SUMMARY_TEMPLATES: dict[str, str] = {
    "meeting": """
Use the default meeting-notes structure. Focus on decisions, action items,
open questions, risks, important details, and a concise follow-up email.
""".strip(),
    "engineering": """
Optimize the notes for an engineering discussion. Preserve technical decisions,
implementation details, owners, blockers, risks, open questions, branch/PR/test
references, rollout concerns, and follow-up work. Avoid polishing away uncertainty.
""".strip(),
    "sales": """
Optimize the notes for a sales or customer call. Preserve customer goals,
pain points, objections, stakeholders, buying signals, risks, competitors,
commercial details, next steps, owners, and follow-up messaging.
""".strip(),
    "interview": """
Optimize the notes for an interview. Preserve candidate/background details,
question themes, evidence, strengths, concerns, follow-ups, and hiring signals.
Do not infer protected characteristics or unsupported evaluations.
""".strip(),
    "executive": """
Optimize the notes for an executive brief. Lead with outcomes, decisions,
strategic risks, owner-level action items, unresolved decisions, dates, numbers,
and concise context. Keep the output skimmable.
""".strip(),
    "legal": """
Optimize the notes for a legal or client matter. Preserve exact dates, obligations,
open questions, cited documents, responsible parties, risks, and uncertainty.
Do not invent legal conclusions.
""".strip(),
}


def available_template_names() -> list[str]:
    return sorted(SUMMARY_TEMPLATES)


def get_summary_template(name: str | None) -> tuple[str, str]:
    normalized = (name or DEFAULT_TEMPLATE).strip().lower()
    if normalized not in SUMMARY_TEMPLATES:
        normalized = DEFAULT_TEMPLATE
    return normalized, SUMMARY_TEMPLATES[normalized]
