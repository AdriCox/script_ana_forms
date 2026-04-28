import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_INPUT_DIR = Path("input/pdfs")
DEFAULT_JSON_DIR = Path("output/json")
DEFAULT_LOG_PATH = Path("output/ingestion_log.json")
DEFAULT_SCHEMA_PATH = Path("config/form_schema.json")
DEFAULT_SCREENSHOT_DIR = Path("output/screenshots")


def load_log(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    with log_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_log(log_path: Path, data: list[dict[str, Any]]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def already_completed(log_entries: list[dict[str, Any]], patient_name: str) -> bool:
    for entry in log_entries:
        if entry.get("patient") == patient_name and entry.get("status") == "completed":
            return True
    return False


def run_extract(pdf_path: Path, output_dir: Path, schema_path: Path) -> Path:
    cmd = [
        "python",
        "src/extract_from_pdf.py",
        "--pdf",
        str(pdf_path),
        "--output-dir",
        str(output_dir),
        "--schema",
        str(schema_path),
    ]
    subprocess.run(cmd, check=True)
    return output_dir / f"{pdf_path.stem}.json"


def run_fill(json_path: Path, schema_path: Path, screenshot_dir: Path, headless: bool) -> dict[str, Any]:
    cmd = [
        "python",
        "src/fill_redcap.py",
        "--json",
        str(json_path),
        "--schema",
        str(schema_path),
        "--screenshot-dir",
        str(screenshot_dir),
        "--auto-close",
    ]
    if headless:
        cmd.append("--headless")

    completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    stdout = completed.stdout.strip()
    if completed.returncode != 0:
        return {
            "status": "failed",
            "error": completed.stderr.strip() or stdout or "Unknown fill error.",
            "submitted_at": datetime.utcnow().isoformat() + "Z",
        }
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "status": "failed",
            "error": f"Unexpected fill output: {stdout}",
            "submitted_at": datetime.utcnow().isoformat() + "Z",
        }


def build_log_entry(patient: str, pdf_path: Path, json_path: Path, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "patient": patient,
        "source_pdf": str(pdf_path),
        "json_path": str(json_path),
        "status": result.get("status", "failed"),
        "record_id": result.get("record_id"),
        "error": result.get("error"),
        "screenshot": result.get("screenshot"),
        "submitted_at": result.get("submitted_at"),
        "logged_at": datetime.utcnow().isoformat() + "Z",
    }


def process_batch(
    input_dir: Path,
    json_dir: Path,
    log_path: Path,
    schema_path: Path,
    screenshot_dir: Path,
    skip_completed: bool,
    headless: bool,
) -> list[dict[str, Any]]:
    pdf_paths = sorted(input_dir.glob("*.pdf"))
    log_entries = load_log(log_path)
    if not pdf_paths:
        return log_entries

    for pdf_path in pdf_paths:
        patient = pdf_path.stem
        if skip_completed and already_completed(log_entries, patient):
            log_entries.append(
                {
                    "patient": patient,
                    "source_pdf": str(pdf_path),
                    "status": "skipped",
                    "reason": "already_completed",
                    "logged_at": datetime.utcnow().isoformat() + "Z",
                }
            )
            write_log(log_path, log_entries)
            continue

        try:
            json_path = run_extract(pdf_path, json_dir, schema_path)
            fill_result = run_fill(json_path, schema_path, screenshot_dir, headless=headless)
        except subprocess.CalledProcessError as error:
            fill_result = {
                "status": "failed",
                "error": f"Extraction failed: {error}",
                "submitted_at": datetime.utcnow().isoformat() + "Z",
            }
            json_path = json_dir / f"{pdf_path.stem}.json"

        log_entries.append(build_log_entry(patient, pdf_path, json_path, fill_result))
        write_log(log_path, log_entries)

    return log_entries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process patient PDFs and submit to REDCap in batch.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR, help="Input PDF folder.")
    parser.add_argument("--json-dir", type=Path, default=DEFAULT_JSON_DIR, help="Output JSON folder.")
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH, help="Ingestion log path.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH, help="Schema path.")
    parser.add_argument(
        "--screenshot-dir",
        type=Path,
        default=DEFAULT_SCREENSHOT_DIR,
        help="Error screenshots folder.",
    )
    parser.add_argument(
        "--no-skip-completed",
        action="store_true",
        help="Do not skip patients already completed in log.",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser headless.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print("Aviso: el scraper actual es manual y parcial; el modo batch no se recomienda para uso desatendido.")
    entries = process_batch(
        input_dir=args.input_dir,
        json_dir=args.json_dir,
        log_path=args.log_path,
        schema_path=args.schema,
        screenshot_dir=args.screenshot_dir,
        skip_completed=not args.no_skip_completed,
        headless=args.headless,
    )
    print(f"Batch finished. Total log entries: {len(entries)}")
