"""
AuditReporter — writes human-readable JSON reports for every snapshot.

Per-snapshot:
  snap_dir/crop_analysis.json   — quality scores per crop
  snap_dir/match_report.json    — match decisions per crop

Aggregate (appended):
  memory_data/reports/ambiguous.jsonl
  memory_data/reports/failed_crops.jsonl
"""
import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

import app.config as config
from app.memory.crop_extractor import CropRecord
from app.memory.crop_quality import QualityResult
from app.memory.descriptor_extractor import DescriptorRecord
from app.memory.identity_matcher import MatchResult

log = logging.getLogger(__name__)


class AuditReporter:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._reports = Path(base_dir or config.MEMORY_DATA_DIR) / "reports"
        self._reports.mkdir(parents=True, exist_ok=True)

    def write_snapshot_report(
        self,
        snap_dir: Path,
        snapshot_id: str,
        crop_records: List[CropRecord],
        quality_results: List[QualityResult],
        descriptors: List[Optional[DescriptorRecord]],
        match_results: List[Optional[MatchResult]],
        uid_assignments: List[Optional[str]],
    ) -> None:
        ts    = int(time.time() * 1000)
        q_map = {q.crop_id: q for q in quality_results}

        # ── crop_analysis.json ───────────────────────────────────────────────
        crop_analysis = []
        for rec in crop_records:
            q = q_map.get(rec.crop_id)
            crop_analysis.append({
                "crop_id":           rec.crop_id,
                "label":             rec.label,
                "confidence":        rec.confidence,
                "clipped":           rec.clipped,
                "quality_score":     q.quality_score        if q else None,
                "blur_score":        q.blur_score           if q else None,
                "accept_for_memory": q.accept_for_memory    if q else False,
                "rejection_reasons": q.rejection_reasons    if q else ["no_quality_result"],
            })
        (snap_dir / "crop_analysis.json").write_text(
            json.dumps(
                {"snapshot_id": snapshot_id, "generated_at": ts, "crops": crop_analysis},
                indent=2,
            )
        )

        # ── match_report.json ────────────────────────────────────────────────
        match_entries = []
        for i, rec in enumerate(crop_records):
            m   = match_results[i]   if i < len(match_results)   else None
            d   = descriptors[i]     if i < len(descriptors)     else None
            uid = uid_assignments[i] if i < len(uid_assignments) else None
            match_entries.append({
                "crop_id":         rec.crop_id,
                "label":           rec.label,
                "decision":        m.decision        if m else "skipped_low_quality",
                "matched_uid":     m.matched_uid     if m else None,
                "assigned_uid":    uid,
                "composite_score": m.composite_score if m else None,
                "candidates":      [asdict(c) for c in m.candidates] if m else [],
                "descriptor_ok":   d is not None,
            })
        (snap_dir / "match_report.json").write_text(
            json.dumps(
                {"snapshot_id": snapshot_id, "generated_at": ts, "matches": match_entries},
                indent=2,
            )
        )

        # ── aggregate JSONL logs ─────────────────────────────────────────────
        for m in match_results:
            if m and m.decision == "ambiguous_candidate":
                self._append_jsonl("ambiguous.jsonl", {
                    "ts": ts, "snapshot_id": snapshot_id,
                    "crop_id": m.crop_id, "best_uid": m.matched_uid,
                    "score": m.composite_score,
                })

        for q in quality_results:
            if not q.accept_for_memory:
                self._append_jsonl("failed_crops.jsonl", {
                    "ts": ts, "snapshot_id": snapshot_id,
                    "crop_id": q.crop_id,
                    "reasons": q.rejection_reasons,
                    "quality_score": q.quality_score,
                })

        accepted = sum(1 for q in quality_results if q.accept_for_memory)
        known    = sum(1 for m in match_results if m and m.decision == "known_match")
        new_obj  = sum(1 for m in match_results if m and m.decision == "new_object")
        ambig    = sum(1 for m in match_results if m and m.decision == "ambiguous_candidate")
        log.info(
            "audit_reporter: snap=%s  crops=%d  accepted=%d  known=%d  new=%d  ambiguous=%d",
            snapshot_id, len(crop_records), accepted, known, new_obj, ambig,
        )

    def _append_jsonl(self, filename: str, record: dict) -> None:
        path = self._reports / filename
        with path.open("a") as f:
            f.write(json.dumps(record) + "\n")
