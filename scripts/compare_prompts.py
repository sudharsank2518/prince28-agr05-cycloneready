"""Compare versioned classification prompts against the evaluation test set."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from cycloneready.config import get_settings
from cycloneready.llm import create_llm_gateway
from cycloneready.llm.classify import accuracy, classify, find_leaks
from cycloneready.llm.prompts import list_versions, load_prompt

ROOT = Path(__file__).resolve().parents[1]
TESTSET = ROOT / "eval" / "prompt_testset.jsonl"
CACHE = ROOT / "eval" / "cache" / "classify.json"
NOTES = ROOT / "NOTES.md"

VALID_LABELS = {"docs", "personal", "off_topic"}
START_MARKER = "<!-- PROMPT COMPARISON START -->"
END_MARKER = "<!-- PROMPT COMPARISON END -->"


def load_testset() -> list[dict[str, str]]:
    """Load and validate the JSONL evaluation questions."""
    if not TESTSET.is_file():
        raise FileNotFoundError(f"Test set not found: {TESTSET}")

    rows = []
    for line_number, line in enumerate(TESTSET.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on test-set line {line_number}: {exc}") from exc

        if not isinstance(row, dict):
            raise ValueError(f"Line {line_number} must contain a JSON object.")

        question = row.get("question")
        label = row.get("label")

        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"Line {line_number} has a missing/empty question.")
        if label not in VALID_LABELS:
            raise ValueError(f"Line {line_number} has invalid label {label!r}.")

        rows.append({"question": question.strip(), "label": label})

    if len(rows) != 20:
        raise ValueError(f"Expected exactly 20 questions, found {len(rows)}.")

    return rows


def load_cache() -> dict[str, Any]:
    """Load previous successful evaluations, if available."""
    if not CACHE.exists():
        return {"results": {}}

    try:
        data = json.loads(CACHE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Evaluation cache is invalid JSON: {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("results"), dict):
        raise ValueError("Evaluation cache has an unexpected format.")

    return data


def save_cache(cache: dict[str, Any]) -> None:
    """Write cache atomically so interrupted runs retain earlier results."""
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    temporary = CACHE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(CACHE)


def prepare_versions(rows: list[dict[str, str]]) -> dict[str, str]:
    """Load prompts and report any test-set leakage."""
    versions = list_versions("classify")
    if not versions:
        raise ValueError("No classify prompt versions were found.")

    prompts = {}
    questions = [row["question"] for row in rows]

    for version in versions:
        prompt = load_prompt("classify", version)
        prompts[version] = prompt
        leaks = find_leaks(prompt, questions)
        print(f"v{version}: {len(leaks)} test-set leak(s)")
        for question in leaks:
            print(f"  LEAK: {question}")

    return prompts


def show_check(rows: list[dict[str, str]], prompts: dict[str, str]) -> None:
    """Validate the inputs without contacting an LLM provider."""
    print(f"\nTest-set questions: {len(rows)}")
    print(f"Prompt versions: {', '.join('v' + v for v in prompts)}")
    print("Label counts:")
    for label in sorted(VALID_LABELS):
        count = sum(row["label"] == label for row in rows)
        print(f"  {label}: {count}")
    print("\nCheck passed. No API calls were made.")


def confusion_table(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Count predictions grouped by actual and predicted labels."""
    predicted_labels = sorted(VALID_LABELS) + ["invalid"]
    table = {
        label: {predicted: 0 for predicted in predicted_labels} for label in sorted(VALID_LABELS)
    }

    for row in rows:
        actual = row.get("label")
        predicted = row.get("got")

        if actual not in VALID_LABELS or predicted not in predicted_labels:
            continue

        table[actual][predicted] += 1

    return table


def update_notes(results: dict[str, list[dict[str, Any]]]) -> None:
    """Replace only the generated comparison section in NOTES.md."""
    lines = [
        START_MARKER,
        "### Prompt comparison results",
        "",
        "| Version | Correct | Evaluated | Accuracy | Incorrect |",
        "|---|---:|---:|---:|---:|",
    ]

    for version, rows in results.items():
        evaluated = [row for row in rows if row.get("got") in VALID_LABELS]
        correct = sum(row["got"] == row["label"] for row in evaluated)
        incorrect = len(evaluated) - correct
        score = accuracy(evaluated)
        lines.append(f"| v{version} | {correct} | {len(evaluated)} | {score:.1%} | {incorrect} |")

    lines.extend(["", "#### Per-label confusion tables", ""])
    predicted_labels = sorted(VALID_LABELS) + ["invalid"]

    for version, rows in results.items():
        table = confusion_table(rows)
        lines.append(f"**v{version}**")
        lines.append("| Actual \\ Predicted | " + " | ".join(predicted_labels) + " |")
        lines.append("|---|" + "---:|" * len(predicted_labels))

        for actual in sorted(VALID_LABELS):
            counts = [str(table[actual][predicted]) for predicted in predicted_labels]
            lines.append(f"| {actual} | " + " | ".join(counts) + " |")

        lines.append("")

    lines.extend(["#### Incorrect predictions", ""])

    for version, rows in results.items():
        misses = [
            row for row in rows if row.get("got") in VALID_LABELS and row["got"] != row["label"]
        ]
        lines.append(f"**v{version}**")
        if not misses:
            lines.append("- No incorrect predictions.")
        else:
            for row in misses:
                lines.append(
                    f"- Expected `{row['label']}`, predicted `{row['got']}`: {row['question']}"
                )
        lines.append("")

    lines.extend(
        [
            "Failed API calls are not included in accuracy. "
            "Rerun the script to retry missing evaluations.",
            END_MARKER,
        ]
    )
    section = "\n".join(lines)

    existing = NOTES.read_text(encoding="utf-8") if NOTES.exists() else ""

    if START_MARKER in existing and END_MARKER in existing:
        before = existing.split(START_MARKER, 1)[0]
        after = existing.split(END_MARKER, 1)[1]
        updated = before + section + after
    else:
        updated = existing.rstrip() + "\n\n" + section + "\n"

    NOTES.write_text(updated, encoding="utf-8")


async def run_comparison(
    prompts: dict[str, str],
    testset: list[dict[str, str]],
) -> None:
    """Evaluate missing prompt/question pairs and cache every success."""
    cache = load_cache()
    results = cache["results"]
    gateway = create_llm_gateway(get_settings())
    total = len(prompts) * len(testset)
    completed = 0

    for version, prompt in prompts.items():
        version_results = results.setdefault(version, [])
        indexed = {item.get("index"): item for item in version_results if isinstance(item, dict)}

        for index, row in enumerate(testset):
            cached = indexed.get(index)

            if (
                cached
                and cached.get("question") == row["question"]
                and cached.get("label") == row["label"]
                and cached.get("got") in VALID_LABELS | {"invalid"}
            ):
                completed += 1
                continue

            print(f"\\n[{completed + 1}/{total}] Prompt v{version}, question {index + 1}/20")

            try:
                predicted, response = await classify(gateway, prompt, version, row["question"])
                item = {
                    "index": index,
                    "question": row["question"],
                    "label": row["label"],
                    "got": predicted,
                    "provider": getattr(response, "provider", None),
                    "error": None,
                }
                indexed[index] = item
                completed += 1
                results[version] = [indexed[i] for i in sorted(indexed)]
                save_cache(cache)
                print(f"Expected: {row['label']} | Predicted: {predicted}")

            except Exception as exc:
                print(f"Request failed: {type(exc).__name__}: {exc}")
                # Keep earlier successful results; failed calls remain uncached.

            if completed < total:
                await asyncio.sleep(5)

        results[version] = [indexed[i] for i in sorted(indexed)]
        save_cache(cache)

    successful = {version: rows for version, rows in results.items() if version in prompts}
    update_notes(successful)

    print("\\nFinal accuracy:")
    for version, rows in successful.items():
        evaluated = [row for row in rows if row.get("got") in VALID_LABELS]
        correct = sum(row["got"] == row["label"] for row in evaluated)
        print(f"v{version}: {correct}/{len(evaluated)} ({accuracy(evaluated):.1%})")
        missing = len(testset) - len(evaluated)
        if missing:
            print(f"  Missing evaluations: {missing}")

    print(f"\\nCache saved to: {CACHE}")
    print(f"Comparison table updated in: {NOTES}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare classification prompt versions.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate prompts and test set without making API calls.",
    )
    args = parser.parse_args()

    testset = load_testset()
    prompts = prepare_versions(testset)

    if args.check:
        show_check(testset, prompts)
        return

    asyncio.run(run_comparison(prompts, testset))


if __name__ == "__main__":
    main()
