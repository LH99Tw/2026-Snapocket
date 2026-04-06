#!/usr/bin/env python3
"""Benchmark /v1/infer latency and compare BF16/Q8 report quality."""

from __future__ import annotations

import argparse
import json
import math
import mimetypes
import re
import socket
import sys
import time
import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

MODEL_ID_BY_ENGINE = {
    "paddle": "llamacpp-paddleocr-vl",
    "glm": "llamacpp-glm-ocr",
}
CRITICAL_LINE_RE = re.compile(r"[\d/:\-%₩$]")
NORMALIZE_RE = re.compile(r"\s+")
SIMPLIFY_RE = re.compile(r"[^0-9a-z가-힣]+", re.IGNORECASE)


@dataclass
class Sample:
    run: int
    warmup: bool
    status_code: int
    wall_ms: int
    latency_ms: int
    ocr_ms: int
    blocks: int
    text_len: int
    confidence: float
    corrected_text: str
    error: str


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _build_multipart(*, fields: dict[str, str], file_field: str, filename: str, content_type: str, payload: bytes) -> tuple[bytes, str]:
    boundary = f"----snapocket-bench-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode("utf-8")
        )

    chunks.append(f"--{boundary}\r\n".encode("utf-8"))
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(payload)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(chunks)
    return body, f"multipart/form-data; boundary={boundary}"


def _http_json(method: str, url: str, *, payload: bytes | None = None, content_type: str | None = None, timeout_s: float = 120.0) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    req = urlrequest.Request(url=url, data=payload, method=method.upper(), headers=headers)
    try:
        with urlrequest.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = int(resp.status)
    except urlerror.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp is not None else ""
        status = int(exc.code)
    except (TimeoutError, socket.timeout):
        return 0, {"error": {"code": "TIMEOUT", "message": f"request timeout after {timeout_s:.1f}s"}}
    except urlerror.URLError as exc:
        return 0, {"error": {"code": "NETWORK_ERROR", "message": str(exc.reason)}}

    raw = raw.strip()
    if not raw:
        return status, {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return status, {"error": {"code": "NON_JSON_RESPONSE", "message": raw[:600]}}
    if not isinstance(parsed, dict):
        return status, {"error": {"code": "UNEXPECTED_JSON_SHAPE", "message": str(type(parsed))}}
    return status, parsed


def _unwrap_data(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("ok") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _extract_error(payload: dict[str, Any], fallback: str = "unknown error") -> str:
    err = payload.get("error")
    if isinstance(err, str):
        return err
    if isinstance(err, dict):
        code = str(err.get("code", "")).strip()
        msg = str(err.get("message", "")).strip()
        if code and msg:
            return f"{code}: {msg}"
        if msg:
            return msg
    detail = payload.get("detail")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    return fallback


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    sorted_vals = sorted(values)
    rank = max(1, int(math.ceil(p * len(sorted_vals))))
    idx = min(len(sorted_vals) - 1, rank - 1)
    return int(sorted_vals[idx])


def _summary(samples: list[Sample]) -> dict[str, Any]:
    ok_samples = [s for s in samples if not s.warmup and s.status_code == 200 and not s.error]
    fail_samples = [s for s in samples if not s.warmup and (s.status_code != 200 or bool(s.error))]

    def vals(name: str) -> list[int]:
        return [int(getattr(s, name)) for s in ok_samples if int(getattr(s, name)) >= 0]

    latency = vals("latency_ms")
    ocr = vals("ocr_ms")
    blocks = vals("blocks")
    text_len = vals("text_len")
    wall = vals("wall_ms")

    return {
        "runs": len([s for s in samples if not s.warmup]),
        "ok_runs": len(ok_samples),
        "failed_runs": len(fail_samples),
        "latency_ms": {"p50": _percentile(latency, 0.50), "p95": _percentile(latency, 0.95)},
        "ocr_ms": {"p50": _percentile(ocr, 0.50), "p95": _percentile(ocr, 0.95)},
        "wall_ms": {"p50": _percentile(wall, 0.50), "p95": _percentile(wall, 0.95)},
        "blocks": {"p50": _percentile(blocks, 0.50), "p95": _percentile(blocks, 0.95)},
        "text_len": {"p50": _percentile(text_len, 0.50), "p95": _percentile(text_len, 0.95)},
    }


def _print_summary(summary: dict[str, Any]) -> None:
    print("")
    print("runs:", summary["runs"], "ok:", summary["ok_runs"], "failed:", summary["failed_runs"])
    print("")
    print(f"{'metric':<12} {'p50':>8} {'p95':>8}")
    print("-" * 31)
    for key in ("latency_ms", "ocr_ms", "wall_ms", "blocks", "text_len"):
        row = summary[key]
        print(f"{key:<12} {int(row['p50']):>8} {int(row['p95']):>8}")
    print("")


def _ensure_active_engine(base_url: str, engine: str, timeout_s: float) -> None:
    model_id = MODEL_ID_BY_ENGINE.get(engine)
    if not model_id:
        return
    status, payload = _http_json(
        "POST",
        f"{base_url.rstrip('/')}/v1/models/{model_id}/activate",
        payload=b"",
        content_type="application/json",
        timeout_s=timeout_s,
    )
    if status >= 400:
        raise RuntimeError(f"failed to activate {engine}: {_extract_error(payload, f'HTTP {status}')}")


def run_benchmark(args: argparse.Namespace) -> int:
    file_path = Path(args.file).resolve()
    if not file_path.exists():
        print(f"[error] input file not found: {file_path}", file=sys.stderr)
        return 2

    base_bytes = file_path.read_bytes()
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    base_url = args.base_url.rstrip("/")
    total_runs = int(args.warmup) + int(args.runs)

    if args.ensure_active in {"paddle", "glm"}:
        _ensure_active_engine(base_url, args.ensure_active, args.timeout_s)

    samples: list[Sample] = []
    for i in range(total_runs):
        warmup = i < int(args.warmup)
        run_no = i + 1
        payload = base_bytes
        if args.cache_bust:
            marker = f"\nbench-run:{run_no}:{uuid.uuid4().hex}\n".encode("utf-8")
            payload = base_bytes + marker

        form_fields = {
            "engine_hint": args.engine_hint,
            "doc_id": f"bench-{int(time.time())}-{run_no}",
        }
        body, content_type = _build_multipart(
            fields=form_fields,
            file_field="file",
            filename=file_path.name,
            content_type=mime,
            payload=payload,
        )

        started = time.perf_counter()
        status, response = _http_json(
            "POST",
            f"{base_url}/v1/infer",
            payload=body,
            content_type=content_type,
            timeout_s=args.timeout_s,
        )
        wall_ms = int((time.perf_counter() - started) * 1000)

        data = _unwrap_data(response)
        has_payload_error = isinstance(data.get("error"), (str, dict))
        if status != 200 or has_payload_error:
            fallback = f"HTTP {status}" if status > 0 else "request failed"
            error = _extract_error(data, fallback)
            sample = Sample(
                run=run_no,
                warmup=warmup,
                status_code=status,
                wall_ms=wall_ms,
                latency_ms=-1,
                ocr_ms=-1,
                blocks=0,
                text_len=0,
                confidence=0.0,
                corrected_text="",
                error=error,
            )
            samples.append(sample)
            state = "warmup" if warmup else "run"
            print(f"[{state} {run_no}] status={status} wall_ms={wall_ms} error={error}")
            if args.strict and not warmup:
                break
            continue

        step = data.get("step_timings") if isinstance(data.get("step_timings"), dict) else {}
        corrected_text = str(data.get("corrected_text") or "")
        blocks = data.get("blocks") if isinstance(data.get("blocks"), list) else []
        sample = Sample(
            run=run_no,
            warmup=warmup,
            status_code=status,
            wall_ms=wall_ms,
            latency_ms=int(data.get("latency_ms") or -1),
            ocr_ms=int(step.get("ocr_ms") or -1),
            blocks=len(blocks),
            text_len=len(corrected_text),
            confidence=float(data.get("confidence") or 0.0),
            corrected_text=corrected_text,
            error="",
        )
        samples.append(sample)
        state = "warmup" if warmup else "run"
        print(
            f"[{state} {run_no}] status={status} latency_ms={sample.latency_ms} "
            f"ocr_ms={sample.ocr_ms} blocks={sample.blocks} text_len={sample.text_len}"
        )

    summary = _summary(samples)
    _print_summary(summary)
    report = {
        "created_at": _now_iso(),
        "label": args.label,
        "base_url": base_url,
        "file": str(file_path),
        "engine_hint": args.engine_hint,
        "ensure_active": args.ensure_active,
        "runs": args.runs,
        "warmup": args.warmup,
        "cache_bust": bool(args.cache_bust),
        "summary": summary,
        "samples": [s.__dict__ for s in samples],
    }

    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report saved: {out}")

    if args.strict and summary["failed_runs"] > 0:
        return 1
    return 0


def _normalize_text(text: str) -> str:
    stripped = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(stripped)


def _simplify(text: str) -> str:
    return SIMPLIFY_RE.sub("", text.lower()).strip()


def _line_sim(left: str, right: str) -> float:
    a = _simplify(left)
    b = _simplify(right)
    if not a or not b:
        return 0.0
    return float(SequenceMatcher(None, a, b).ratio())


def _representative_text(report: dict[str, Any]) -> tuple[str, int]:
    samples = report.get("samples") or []
    valid = [s for s in samples if not s.get("warmup") and s.get("status_code") == 200 and not s.get("error")]
    if not valid:
        return "", 0
    mids = sorted(valid, key=lambda s: int(s.get("latency_ms", 0)))
    rep = mids[len(mids) // 2]
    return str(rep.get("corrected_text") or ""), int(rep.get("blocks") or 0)


def compare_reports(args: argparse.Namespace) -> int:
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    cand = json.loads(Path(args.candidate).read_text(encoding="utf-8"))

    base_summary = base.get("summary", {})
    cand_summary = cand.get("summary", {})

    base_text, base_blocks = _representative_text(base)
    cand_text, cand_blocks = _representative_text(cand)

    base_norm = _normalize_text(base_text)
    cand_norm = _normalize_text(cand_text)
    similarity = float(SequenceMatcher(None, base_norm, cand_norm).ratio()) if base_norm and cand_norm else 0.0

    base_lines = [line for line in base_norm.splitlines() if line.strip()]
    cand_lines = [line for line in cand_norm.splitlines() if line.strip()]
    critical_lines = [line for line in base_lines if CRITICAL_LINE_RE.search(line)]

    missing_critical = 0
    for line in critical_lines:
        if not cand_lines:
            missing_critical += 1
            continue
        best = max(_line_sim(line, c) for c in cand_lines)
        if best < float(args.critical_line_similarity):
            missing_critical += 1

    block_ratio = float(cand_blocks) / float(base_blocks) if base_blocks > 0 else 1.0

    cand_p95 = int((cand_summary.get("latency_ms") or {}).get("p95") or 0)
    cand_ocr_p95 = int((cand_summary.get("ocr_ms") or {}).get("p95") or 0)
    speed_ok = cand_p95 <= int(args.target_p95_ms)
    ocr_ok = cand_ocr_p95 <= int(args.target_ocr_p95_ms)
    similarity_ok = similarity >= float(args.min_similarity)
    critical_ok = missing_critical == 0
    block_ok = block_ratio >= float(args.min_block_ratio)

    verdict = speed_ok and ocr_ok and similarity_ok and critical_ok and block_ok
    result = {
        "baseline_report": str(Path(args.baseline).resolve()),
        "candidate_report": str(Path(args.candidate).resolve()),
        "candidate_p95_ms": cand_p95,
        "candidate_ocr_p95_ms": cand_ocr_p95,
        "text_similarity": round(similarity, 6),
        "missing_critical_lines": missing_critical,
        "critical_line_count": len(critical_lines),
        "block_ratio": round(block_ratio, 6),
        "checks": {
            "speed_ok": speed_ok,
            "ocr_ok": ocr_ok,
            "similarity_ok": similarity_ok,
            "critical_ok": critical_ok,
            "block_ok": block_ok,
        },
        "verdict": verdict,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"compare report saved: {out}")

    return 0 if verdict else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark and compare /v1/infer runs")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Run benchmark against /v1/infer")
    run.add_argument("--base-url", default="http://127.0.0.1:18080")
    run.add_argument("--file", default="../data/testdata/test.png")
    run.add_argument("--engine-hint", default="auto")
    run.add_argument("--ensure-active", choices=("none", "paddle", "glm"), default="paddle")
    run.add_argument("--runs", type=int, default=20)
    run.add_argument("--warmup", type=int, default=1)
    run.add_argument("--timeout-s", type=float, default=180.0)
    run.add_argument("--label", default="bench")
    run.add_argument("--output", default="")
    run.add_argument("--strict", action="store_true")
    run.add_argument("--cache-bust", action=argparse.BooleanOptionalAction, default=True)

    compare = sub.add_parser("compare", help="Compare baseline/candidate benchmark reports")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--target-p95-ms", type=int, default=5000)
    compare.add_argument("--target-ocr-p95-ms", type=int, default=4500)
    compare.add_argument("--min-similarity", type=float, default=0.95)
    compare.add_argument("--critical-line-similarity", type=float, default=0.75)
    compare.add_argument("--min-block-ratio", type=float, default=0.8)
    compare.add_argument("--output", default="")

    args = parser.parse_args()
    if args.cmd == "run":
        return run_benchmark(args)
    if args.cmd == "compare":
        return compare_reports(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
