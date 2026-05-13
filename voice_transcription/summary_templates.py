from __future__ import annotations

from pathlib import Path

from .config import BASE_DIR

DEFAULT_TEMPLATE = "meeting"
CUSTOM_TEMPLATE_DIR = BASE_DIR / "templates"

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


def _custom_template_candidates(name: str, template_dir: Path) -> list[Path]:
    candidate = Path(name).expanduser()
    candidates: list[Path] = []

    if candidate.suffix.lower() == ".md":
        candidates.append(candidate)
    else:
        candidates.append(template_dir / f"{name}.md")
        candidates.append(template_dir / name)

    return candidates


def _read_custom_template(path: Path) -> tuple[str, str] | None:
    try:
        if not path.exists() or not path.is_file():
            return None
        text = path.read_text(encoding="utf-8").strip()
    except Exception:
        return None

    if not text:
        return None

    return path.stem, text


def available_template_names(template_dir: Path = CUSTOM_TEMPLATE_DIR) -> list[str]:
    names = set(SUMMARY_TEMPLATES)
    if template_dir.exists():
        for path in template_dir.glob("*.md"):
            if path.is_file() and path.name != "README.md":
                names.add(path.stem)
    return sorted(names)


def get_summary_template(name: str | None, template_dir: Path = CUSTOM_TEMPLATE_DIR) -> tuple[str, str]:
    normalized = (name or DEFAULT_TEMPLATE).strip().lower()
    if normalized in SUMMARY_TEMPLATES:
        return normalized, SUMMARY_TEMPLATES[normalized]

    requested = (name or "").strip()
    for candidate in _custom_template_candidates(requested, template_dir):
        custom_template = _read_custom_template(candidate)
        if custom_template:
            return custom_template

    return DEFAULT_TEMPLATE, SUMMARY_TEMPLATES[DEFAULT_TEMPLATE]
