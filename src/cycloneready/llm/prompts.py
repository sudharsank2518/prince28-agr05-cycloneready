"""Load and discover versioned LLM prompts."""

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


def list_versions(task: str) -> list[str]:
    """Find available prompt versions and return them in sorted order."""
    pattern = f"{task}_v*.md"
    files = sorted(
        PROMPTS_DIR.glob(pattern),
        key=lambda path: int(path.stem.rsplit("_v", 1)[1]),
    )
    return [path.stem.rsplit("_v", 1)[1] for path in files]


def load_prompt(task: str, version: str) -> str:
    """Load a particular version of a prompt."""
    path = PROMPTS_DIR / f"{task}_v{version}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")
