"""Validate a completed model card and its digest-pinned local evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MAX_DOCUMENT_BYTES = 4 * 1024 * 1024


def _load_json(path: Path) -> dict:
    if path.stat().st_size > _MAX_DOCUMENT_BYTES:
        raise ValueError(f"JSON document exceeds {_MAX_DOCUMENT_BYTES} bytes")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("top-level JSON value must be an object")
    return value


def _digest(value, field: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        errors.append(f"{field} must be a lowercase SHA-256 digest")
        return False
    return True


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_file(root: Path, relative_path, expected, field: str, errors: list[str]) -> Path | None:
    if not isinstance(relative_path, str) or not relative_path.strip():
        errors.append(f"{field}.path must be a non-empty repository-relative path")
        return None
    raw = Path(relative_path)
    if raw.is_absolute():
        errors.append(f"{field}.path must be repository-relative")
        return None
    try:
        target = (root / raw).resolve(strict=True)
        target.relative_to(root)
    except (OSError, ValueError):
        errors.append(f"{field}.path must resolve to an existing file inside the repository")
        return None
    if not target.is_file():
        errors.append(f"{field}.path must resolve to a file")
        return None
    if not _digest(expected, f"{field}.sha256", errors):
        return target
    digest = _sha256_file(target)
    if digest != expected:
        errors.append(f"{field}.sha256 does not match {relative_path}")
    return target


def _validate_bundle(root: Path, bundle_path: Path, errors: list[str]) -> None:
    try:
        bundle = _load_json(bundle_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"provenance bundle is not valid JSON: {exc}")
        return
    components = bundle.get("components")
    if not isinstance(components, list) or not components:
        errors.append("provenance bundle.components must be a non-empty list")
    else:
        for index, component in enumerate(components):
            field = f"provenance bundle.components[{index}]"
            if not isinstance(component, dict):
                errors.append(f"{field} must be an object")
                continue
            _digest(component.get("sha256"), f"{field}.sha256", errors)
            if "path" in component:
                _verify_file(root, component.get("path"), component.get("sha256"), field, errors)

    sources = bundle.get("pipeline_sources")
    if not isinstance(sources, dict) or not sources:
        errors.append("provenance bundle.pipeline_sources must be a non-empty object")
    else:
        for path, expected in sources.items():
            field = f"provenance bundle.pipeline_sources[{path!r}]"
            _verify_file(root, path, expected, field, errors)


def validate_model_card(card_path: Path, root: Path | None = None) -> list[str]:
    """Return validation errors; paths in the card are relative to repository root."""
    root = (root or Path.cwd()).resolve(strict=True)
    errors: list[str] = []
    try:
        card = _load_json(card_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"model card is not valid JSON: {exc}"]

    if card.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    for field in ("model_id", "model_version", "intended_use", "task", "architecture"):
        if not isinstance(card.get(field), str) or not card[field].strip():
            errors.append(f"{field} must be a non-empty string")

    weights = card.get("weights")
    if not isinstance(weights, dict):
        errors.append("weights must be an object")
    else:
        _digest(weights.get("sha256"), "weights.sha256", errors)

    pipeline = card.get("pipeline")
    if not isinstance(pipeline, dict):
        errors.append("pipeline must be an object")
    else:
        _digest(pipeline.get("configuration_sha256"), "pipeline.configuration_sha256", errors)
        _digest(pipeline.get("preprocessing_sha256"), "pipeline.preprocessing_sha256", errors)

    data = card.get("data")
    if not isinstance(data, dict):
        errors.append("data must be an object")
    elif not isinstance(data.get("known_coverage_gaps"), list) or not data["known_coverage_gaps"]:
        errors.append("data.known_coverage_gaps must be a non-empty list")

    evaluation = card.get("evaluation")
    if not isinstance(evaluation, dict):
        errors.append("evaluation must be an object")
    else:
        report = _verify_file(root, evaluation.get("report_path"), evaluation.get("report_sha256"),
                              "evaluation.report", errors)
        if report is not None:
            try:
                _load_json(report)
                if evaluation.get("sample_count") is not None and type(evaluation["sample_count"]) is not int:
                    errors.append("evaluation.sample_count must be an integer or null")
                if not isinstance(evaluation.get("limitations"), list) or not evaluation["limitations"]:
                    errors.append("evaluation.limitations must be a non-empty list")
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"evaluation report is not valid JSON: {exc}")

    bundle = card.get("provenance_bundle")
    if bundle is not None:
        if not isinstance(bundle, dict):
            errors.append("provenance_bundle must be an object")
        else:
            bundle_path = _verify_file(root, bundle.get("path"), bundle.get("sha256"),
                                       "provenance_bundle", errors)
            if bundle_path is not None:
                _validate_bundle(root, bundle_path, errors)

    decision = card.get("release_decision")
    if not isinstance(decision, dict) or decision.get("status") not in {"unreviewed", "approved", "rejected"}:
        errors.append("release_decision.status must be unreviewed, approved, or rejected")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_card", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root for relative evidence paths")
    args = parser.parse_args()
    errors = validate_model_card(args.model_card, args.root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"Valid model card: {args.model_card}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
