"""Evidence-first judgment validation and non-compensating score aggregation."""
import json
import math
from pathlib import Path
import unicodedata

PROMPTS = Path(__file__).resolve().parents[1] / "prompts/evaluation"
SYSTEM = (PROMPTS / "system.txt").read_text(encoding="utf-8")
RULES = {axis: (PROMPTS / f"{axis.lower()}.txt").read_text(encoding="utf-8")
         for axis in ("Structure", "Style", "Quality")}
SEVERITY_CAPS = {'none': 100, 'minor': 89, 'moderate': 69, 'major': 39, 'critical': 19}


def aggregate(subscores, checks, axis, weights):
    mean = sum(subscores[key] * weight for key, weight in weights[axis].items())
    score, caps = mean, []
    if axis == "Style":
        score = min(score, subscores["photorealism"])
        if score < mean:
            caps.append("Style cannot exceed photorealism")
    elif axis in ("Structure", "Quality"):
        severe = [SEVERITY_CAPS[c["severity"]] for c in checks.values()
                  if c["severity"] in ("major", "critical")]
        if severe and score > min(severe):
            score = min(severe)
            caps.append("Central major/critical failure ceiling")
    return round(score, 2), round(mean, 2), caps


def check_timestamp(value, duration):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Evidence timestamp is not a valid non-negative number")
    if value <= duration:
        return False
    if value - duration <= .050001 and abs(value * 10 - round(value * 10)) < 1e-8:
        return True
    raise ValueError("Evidence timestamp outside video beyond endpoint rounding")


def validate(raw, axis, weights, metadata, prompt=None):
    text = raw.rsplit("</think>", 1)[-1].strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    data = json.loads(text)
    required = {"subscores", "checks", "evidence", "confidence", "limitations"}
    if not required <= set(data):
        raise ValueError("Evidence-first schema fields are missing or unexpected")
    schema_flags = []
    if set(data) - required:
        schema_flags.append("Additional top-level metadata retained but excluded from score calculation")
    keys = set(weights[axis])
    if set(data["subscores"]) != keys or set(data["checks"]) != keys:
        raise ValueError("Criterion keys do not match the frozen rubric")
    if data["confidence"] not in ("low", "medium", "high"):
        raise ValueError("Invalid confidence")
    if not isinstance(data["limitations"], str) or not data["limitations"].strip():
        raise ValueError("Explicit limitations are required")
    evidence = data["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("At least opening/middle/ending evidence is required")
    repaired = []
    evidence_repairs = []
    index = 0
    while index < len(evidence):
        entry = evidence[index]
        if (entry == "evidence_type" and index + 1 < len(evidence)
                and evidence[index + 1] in ("frame", "interval")
                and repaired and isinstance(repaired[-1], dict)
                and "evidence_type" not in repaired[-1]):
            repaired[-1]["evidence_type"] = evidence[index + 1]
            evidence_repairs.append({"kind": "detached_evidence_type_pair", "observation": len(repaired) - 1,
                                     "value": evidence[index + 1]})
            index += 2
            continue
        if not isinstance(entry, dict):
            raise ValueError("Unrecognized non-object evidence; not guessing its meaning")
        repaired.append(entry)
        index += 1
    evidence = data["evidence"] = repaired
    if evidence_repairs:
        data["evidence_repairs"] = evidence_repairs
    if {e.get("phase") for e in evidence} != {"opening", "middle", "ending"} or len(evidence) < 3:
        schema_flags.append("Evidence does not cover all three required phases; temporal review required")
    combined_style_evidence = False
    timestamp_notes = []
    quote_flags = []
    for number, event in enumerate(evidence):
        if (axis == "Style" and "observation" not in event
                and isinstance(event.get("reference_observation"), str)
                and "candidate" in event["reference_observation"].lower()):
            # The response supplied a combined comparison rather than separate
            # fields. Preserve the exact text and make the normalization explicit.
            event["observation"] = event["reference_observation"]
            combined_style_evidence = True
        expected = {"phase", "seconds", "observation"}
        if axis == "Structure":
            expected |= {"source_seconds", "source_observation", "prompt_clause"}
        elif axis == "Style":
            expected.add("reference_observation")
        if not expected <= set(event):
            raise ValueError("Evidence fields do not match this dimension")
        if set(event) - expected - {"evidence_type", "index", "id"}:
            schema_flags.append(f"evidence {number}: additional metadata retained without using it for scoring")
        if event.get("evidence_type", "frame") not in ("frame", "interval"):
            raise ValueError("Unknown evidence type")
        if "index" in event and (type(event["index"]) is not int or event["index"] < 0):
            raise ValueError("Invalid optional visual-input index")
        if "id" in event and (type(event["id"]) is not int or event["id"] < 0):
            raise ValueError("Invalid optional evidence identifier")
        if check_timestamp(event["seconds"], metadata["candidate"]["duration"]):
            timestamp_notes.append({"evidence": number, "role": "candidate", "reported_seconds": event["seconds"],
                                    "interpretation": "one-decimal clip-end rounding; original timestamp retained"})
        for field in expected - {"phase", "seconds", "source_seconds", "prompt_clause"}:
            if not isinstance(event[field], str) or not event[field].strip():
                raise ValueError("Specific non-empty visual observations required")
        if axis == "Structure":
            if check_timestamp(event["source_seconds"], metadata["threejs"]["duration"]):
                timestamp_notes.append({"evidence": number, "role": "source", "reported_seconds": event["source_seconds"],
                                        "interpretation": "one-decimal clip-end rounding; original timestamp retained"})
            quote = event["prompt_clause"]
            if quote is not None:
                if not isinstance(quote, str) or not quote.strip():
                    raise ValueError("Prompt clause must be a nonempty string or null")
                if prompt is not None and quote not in prompt:
                    normalized_quote = " ".join(unicodedata.normalize("NFKC", quote).casefold().split())
                    normalized_prompt = " ".join(unicodedata.normalize("NFKC", prompt).casefold().split())
                    kind = "format/case variation" if normalized_quote in normalized_prompt else "unverified or paraphrased citation"
                    quote_flags.append(f"evidence {number}: prompt quote is not verbatim ({kind}); original wording retained")
    consistency_flags = []
    consistency_flags.extend(schema_flags)
    consistency_flags.extend(quote_flags)
    if evidence_repairs:
        consistency_flags.append("Detached optional evidence metadata was repaired; raw answer retained")
    if combined_style_evidence:
        data["evidence_normalization"] = "combined_reference_and_candidate_text_preserved_in_both_fields"
        consistency_flags.append("Style observations were combined rather than independently described")
    all_indices = [i for check in data["checks"].values() for i in check.get("evidence_indices", [])]
    one_based = (bool(all_indices) and all(type(i) is int and 1 <= i <= len(evidence) for i in all_indices)
                 and len(evidence) in all_indices)
    if one_based:
        # A uniformly one-based citation convention can be converted without
        # altering observations, subscores or the saved raw API answer.
        data["original_evidence_indices"] = {k: list(c["evidence_indices"]) for k, c in data["checks"].items()}
        for check in data["checks"].values():
            check["evidence_indices"] = [i - 1 for i in check["evidence_indices"]]
        data["citation_normalization"] = "uniform_one_based_to_zero_based"
    for key, value in data["subscores"].items():
        check = data["checks"][key]
        if set(check) != {"severity", "reason", "evidence_indices"}:
            raise ValueError("Every criterion needs severity/reason/evidence links")
        if check["severity"] not in SEVERITY_CAPS:
            raise ValueError("Unknown severity")
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError("Subscore must be a finite number in [0,100]")
        if value > SEVERITY_CAPS[check["severity"]]:
            consistency_flags.append(f"{key}: score exceeds its declared {check['severity']} severity band")
        if not isinstance(check["reason"], str) or not check["reason"].strip():
            raise ValueError("Criterion-specific reason is required")
        if not isinstance(check["evidence_indices"], list) or not check["evidence_indices"]:
            raise ValueError("Uncited criterion")
        if any(type(i) is not int or not 0 <= i < len(evidence) for i in check["evidence_indices"]):
            consistency_flags.append(f"{key}: unresolved evidence indices; retained without guessing")
    if axis == "Structure" and not any(e["prompt_clause"] for e in evidence):
        consistency_flags.append("Prompt alignment has no explicit quoted clause; requires review")
    data["score"], data["uncapped_score"], data["score_caps"] = aggregate(data["subscores"], data["checks"], axis, weights)
    data["consistency_flags"] = consistency_flags
    data["timestamp_notes"] = timestamp_notes
    data["needs_review"] = data["confidence"] == "low" or bool(consistency_flags)
    return data
