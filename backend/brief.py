"""
Onboarding Brief
A one-page orientation for an engineer taking over a repository, written by
the LLM from the architecture map (modules, entry points, risk hotspots) and
the project's README, so every claim is grounded in the indexed code.
"""

import os
import re

from agents.llm import make_llm

BRIEF_PROMPT = """You are writing a one-page onboarding brief for an engineer who is taking over
this repository tomorrow. Use ONLY the facts below; do not invent features or files.

Write markdown with exactly these sections:
## What this project is
(2-3 sentences)
## How it's organized
(one bullet per module: what it contains, naming real files)
## Where to start reading
(3-5 files in reading order, each with one line on why)
## Risky areas
(the hotspots: why each needs care, citing dependents and test coverage)
## Good first tasks
(3 concrete, small tasks that would teach someone the codebase)

Keep it under 450 words. Use `code formatting` for file paths.

REPOSITORY: {name}
LANGUAGES: {languages}
SIZE: {files} source files, {dependencies} internal imports, {classes} classes, {functions} functions,
{test_files} test files, {untested} source files without tests

MODULES (files):
{modules}

ENTRY POINTS:
{entries}

RISK HOTSPOTS (risk 0-100, with reasons):
{hotspots}

README (excerpt):
{readme}
"""


def clean_brief(text: str) -> str:
    """Strip a wrapping ```markdown fence and a leading title; the panel has its own heading."""
    text = text.strip()
    m = re.match(r"^```[\w-]*\n(.*?)\n?```$", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    return re.sub(r"^# [^\n]*\n+", "", text)


def _readme(faiss_store) -> str:
    chunks = [m for m in faiss_store.metadata
              if os.path.basename(m.get("file_path", "")).lower().startswith("readme")]
    chunks.sort(key=lambda m: (m.get("file_path", ""), m.get("start_line") or 0))
    text = "\n".join(c.get("content", "") for c in chunks)
    return text[:3500] or "(no README)"


def generate_brief(name: str, map_data: dict, faiss_store) -> str:
    by_id = {n["id"]: n for n in map_data["nodes"]}
    stats = map_data["stats"]

    modules = []
    for m in map_data["modules"]:
        files = [n for n in map_data["nodes"] if n["module"] == m["name"]]
        files.sort(key=lambda n: -n["fan_in"])
        modules.append(f"- {m['name']} ({m['files']}): " + ", ".join(n["path"] for n in files[:6]))

    entries = [f"- {by_id[i]['path']} (imports {by_id[i]['fan_out']} files)" for i in map_data["entry_points"]]
    hotspots = [f"- {by_id[i]['path']}: risk {by_id[i]['risk']}; {'; '.join(by_id[i]['risk_reasons'])}"
                for i in map_data["hotspots"][:6]]

    prompt = BRIEF_PROMPT.format(
        name=name,
        languages=", ".join(f"{k} ({v})" for k, v in stats["languages"].items()),
        files=stats["files"], dependencies=stats["dependencies"], classes=stats["classes"],
        functions=stats["functions"], test_files=stats["test_files"], untested=stats["untested_files"],
        modules="\n".join(modules) or "(none)",
        entries="\n".join(entries) or "(none detected)",
        hotspots="\n".join(hotspots) or "(none)",
        readme=_readme(faiss_store),
    )
    return clean_brief(make_llm(0.2).invoke(prompt).content)
