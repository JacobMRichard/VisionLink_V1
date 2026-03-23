"""
Standalone pipeline test — exercises the full V2 snapshot pipeline
without starting the HTTP server.

Run: conda run -n visionlink python test_snapshot_pipeline.py
"""
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import sys
import time
import json
import shutil
from pathlib import Path

# ── Use a temp memory dir so tests don't pollute real data ───────────────────
TEST_DIR = Path("test_memory_output")
if TEST_DIR.exists():
    shutil.rmtree(TEST_DIR)
TEST_DIR.mkdir()

# Patch config before imports
import app.config as config
config.MEMORY_DATA_DIR = str(TEST_DIR)

# ── Imports ──────────────────────────────────────────────────────────────────
from app.processing.detect import load_model
from app.memory.snapshot_manager import SnapshotManager
from app.memory.snapshot_detector import run as run_detector
from app.memory.crop_extractor import extract as extract_crops
from app.memory.crop_quality import score_all as score_crops
from app.memory.descriptor_extractor import extract as extract_descriptor
from app.memory.object_memory_store import ObjectMemoryStore
from app.memory.embedding_index import EmbeddingIndex
from app.memory.identity_matcher import IdentityMatcher
from app.memory.memory_updater import MemoryUpdater
from app.memory.audit_reporter import AuditReporter

import cv2
import numpy as np

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

results = []

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    print(f"  {status}  {name}" + (f"  — {detail}" if detail else ""))

def section(title):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")

# ── 1. Create a synthetic test image ─────────────────────────────────────────
section("1. Create test image")
img = np.zeros((720, 1280, 3), dtype=np.uint8)
# Draw two coloured rectangles to give YOLO something (may not detect if no objects)
cv2.rectangle(img, (200, 200), (500, 500), (0, 128, 255), -1)    # orange box
cv2.rectangle(img, (700, 300), (900, 550), (0, 200, 80), -1)     # green box
ret, jpeg_bytes = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
check("synthetic JPEG encoded", ret and len(jpeg_bytes) > 0, f"{len(jpeg_bytes)} bytes")
jpeg_bytes = jpeg_bytes.tobytes()

# ── 2. Load YOLO (warm-up) ───────────────────────────────────────────────────
section("2. YOLO warm-up")
t0 = time.time()
load_model()
elapsed = time.time() - t0
check("YOLO model loaded", True, f"{elapsed:.1f}s")

# ── 3. SnapshotManager ───────────────────────────────────────────────────────
section("3. SnapshotManager")
snap_mgr = SnapshotManager(base_dir=str(TEST_DIR))
snap_id, snap_dir = snap_mgr.save(
    jpeg_bytes=jpeg_bytes,
    frame_id=42,
    timestamp_ms=int(time.time() * 1000),
    width=1280, height=720,
    session_id="test_session",
)
check("snapshot_id assigned",    snap_id == "snap_000001", snap_id)
check("snap_dir created",        snap_dir.exists())
check("full.jpg saved",          (snap_dir / "full.jpg").exists())
check("snapshot_meta.json saved",(snap_dir / "snapshot_meta.json").exists())

meta = json.loads((snap_dir / "snapshot_meta.json").read_text())
check("meta has snapshot_id",    meta.get("snapshot_id") == snap_id)
check("meta has frame_id",       meta.get("frame_id") == 42)

# ── 4. SnapshotDetector ──────────────────────────────────────────────────────
section("4. SnapshotDetector")
t0 = time.time()
detections = run_detector(snap_dir, snap_dir / "full.jpg")
elapsed = time.time() - t0
check("detector ran without error", True, f"{elapsed:.2f}s  detections={len(detections)}")
check("detections.json saved", (snap_dir / "detections.json").exists())
det_data = json.loads((snap_dir / "detections.json").read_text())
check("detections.json is list", isinstance(det_data, list))
# Synthetic image with coloured boxes — YOLO may not detect (that's OK for pipeline test)
print(f"     note: {len(detections)} detections on synthetic image (may be 0, that is OK)")

# ── 5. Inject a fake detection to test rest of pipeline ─────────────────────
section("5. Pipeline with injected detection")
from app.processing.tracked_object import RawDetection
fake_det = RawDetection(
    label="bottle",
    confidence=0.75,
    bbox_x=220, bbox_y=220, bbox_w=260, bbox_h=260,
    centroid_x=350, centroid_y=350,
    floor_score=0.5,
)
test_detections = [fake_det]

# ── 6. CropExtractor ─────────────────────────────────────────────────────────
section("6. CropExtractor")
image = cv2.imread(str(snap_dir / "full.jpg"))
crop_records = extract_crops(snap_dir, snap_id, image, test_detections)
check("at least 1 crop record",  len(crop_records) >= 1, f"got {len(crop_records)}")
if crop_records:
    cr = crop_records[0]
    check("crop image saved",    Path(cr.image_path).exists())
    check("crop_id assigned",    cr.crop_id == "det_0001")
    check("snapshot_id in crop", cr.snapshot_id == snap_id)

# ── 7. CropQuality ───────────────────────────────────────────────────────────
section("7. CropQualityScorer")
quality_results = score_crops(crop_records)
check("quality result for each crop", len(quality_results) == len(crop_records))
if quality_results:
    q = quality_results[0]
    check("quality_score in [0,1]", 0.0 <= q.quality_score <= 1.0, f"{q.quality_score:.3f}")
    check("blur_score > 0",         q.blur_score >= 0, f"{q.blur_score:.1f}")
    print(f"     accept_for_memory={q.accept_for_memory}  reasons={q.rejection_reasons}")

# ── 8. DescriptorExtractor ────────────────────────────────────────────────────
section("8. DescriptorExtractor")
desc = None
if crop_records:
    cr = crop_records[0]
    crop_img = cv2.imread(cr.image_path)
    t0 = time.time()
    desc = extract_descriptor(
        crop_id=cr.crop_id,
        snapshot_id=snap_id,
        label=cr.label,
        confidence=cr.confidence,
        quality_score=quality_results[0].quality_score if quality_results else 0.0,
        image=crop_img,
        frame_area=1280 * 720,
    )
    elapsed = time.time() - t0
    check("descriptor returned",          desc is not None, f"{elapsed:.2f}s")
    if desc:
        check("embedding length 2048",    len(desc.embedding) == 2048)
        check("embedding L2-normalised",  abs(sum(x*x for x in desc.embedding) - 1.0) < 0.01,
              f"norm²={sum(x*x for x in desc.embedding):.4f}")
        check("color_hist length 512",    len(desc.color_hist) == 512, f"len={len(desc.color_hist)}")
        check("color_hist sums to ~1",    abs(sum(desc.color_hist) - 1.0) < 0.01,
              f"sum={sum(desc.color_hist):.4f}")
        check("shape dict has keys",      all(k in desc.shape for k in ("aspect","extent","area_frac")))

# ── 9. ObjectMemoryStore ─────────────────────────────────────────────────────
section("9. ObjectMemoryStore")
store = ObjectMemoryStore(base_dir=str(TEST_DIR))
rec1 = store.create(label="bottle", confidence=0.75)
check("object record created",   rec1 is not None, rec1.object_uid)
check("uid format obj_000001",   rec1.object_uid == "obj_000001")
check("status = provisional",    rec1.status == "provisional")
check("memory JSON on disk",     (TEST_DIR / "objects" / rec1.object_uid / "object_memory.json").exists())

# Reload and verify persistence
loaded = store.load(rec1.object_uid)
check("record reloads correctly", loaded is not None and loaded.object_uid == rec1.object_uid)

# ── 10. EmbeddingIndex ────────────────────────────────────────────────────────
section("10. EmbeddingIndex")
index = EmbeddingIndex(base_dir=str(TEST_DIR))
if desc:
    index.add(desc.embedding, rec1.object_uid)
    check("index size = 1",       index.size == 1)
    results_search = index.search(desc.embedding, k=1)
    check("self-search returns uid", len(results_search) == 1 and results_search[0][0] == rec1.object_uid,
          f"score={results_search[0][1]:.4f}" if results_search else "no results")
    check("self-search score ≈ 1.0", results_search[0][1] > 0.99 if results_search else False,
          f"{results_search[0][1]:.4f}" if results_search else "—")
    check("FAISS index file saved",  (TEST_DIR / "indexes" / "embedding_index.faiss").exists())
    check("embedding_map.json saved",(TEST_DIR / "indexes" / "embedding_map.json").exists())

# ── 11. IdentityMatcher ───────────────────────────────────────────────────────
section("11. IdentityMatcher")
matcher = IdentityMatcher(store, index)
if desc:
    match = matcher.match(desc)
    check("match result returned",        match is not None)
    check("decision is valid string",     match.decision in ("known_match","ambiguous_candidate","new_object"),
          match.decision)
    # Self-match with score ~1.0 should be known_match
    check("self-match → known_match",     match.decision == "known_match",
          f"decision={match.decision}  score={match.composite_score:.3f}")
    check("matched_uid correct",          match.matched_uid == rec1.object_uid)
    check("candidates list populated",    len(match.candidates) >= 1)
    check("score breakdown has fields",   all(hasattr(match.candidates[0], f) for f in
                                             ("embedding_score","color_score","composite_score")) if match.candidates else False)

# ── 12. MemoryUpdater ─────────────────────────────────────────────────────────
section("12. MemoryUpdater")
updater = MemoryUpdater(store, index)
if desc and crop_records and quality_results and match:
    uid = updater.apply(match, desc, crop_records[0], quality_results[0])
    check("apply returns uid",       uid == rec1.object_uid, uid)
    updated = store.load(rec1.object_uid)
    check("times_seen incremented",  updated.times_seen == 2, f"times_seen={updated.times_seen}")

# ── 13. AuditReporter ─────────────────────────────────────────────────────────
section("13. AuditReporter")
reporter = AuditReporter(base_dir=str(TEST_DIR))
match_list  = [match] if (desc and match) else [None]
uid_list    = [uid]   if (desc and match) else [None]
desc_list   = [desc]  if desc else [None]
reporter.write_snapshot_report(
    snap_dir, snap_id,
    crop_records, quality_results,
    desc_list, match_list, uid_list,
)
check("crop_analysis.json written",  (snap_dir / "crop_analysis.json").exists())
check("match_report.json written",   (snap_dir / "match_report.json").exists())

ca = json.loads((snap_dir / "crop_analysis.json").read_text())
check("crop_analysis has crops key", "crops" in ca)
mr = json.loads((snap_dir / "match_report.json").read_text())
check("match_report has matches key","matches" in mr)
if mr["matches"]:
    m0 = mr["matches"][0]
    check("match entry has decision",all(k in m0 for k in ("crop_id","decision","assigned_uid","candidates")))

# ── 14. Directory structure ───────────────────────────────────────────────────
section("14. Output directory structure")
check("snapshots/ exists",   (TEST_DIR / "snapshots").exists())
check("objects/ exists",     (TEST_DIR / "objects").exists())
check("indexes/ exists",     (TEST_DIR / "indexes").exists())
check("reports/ exists",     (TEST_DIR / "reports").exists())
check("exemplars/ exists",   (TEST_DIR / "objects" / rec1.object_uid / "exemplars").exists())
check("evidence/ exists",    (TEST_DIR / "objects" / rec1.object_uid / "evidence").exists())

# ── Summary ───────────────────────────────────────────────────────────────────
section("SUMMARY")
passed = sum(1 for s,_,_ in results if s == PASS)
failed = sum(1 for s,_,_ in results if s == FAIL)
total  = len(results)
print(f"\n  {passed}/{total} checks passed   {failed} failed\n")

if failed > 0:
    print("  FAILED CHECKS:")
    for s, name, detail in results:
        if s == FAIL:
            print(f"    ❌  {name}" + (f"  — {detail}" if detail else ""))
    sys.exit(1)
else:
    print("  All checks passed.\n")

# Cleanup
shutil.rmtree(TEST_DIR)
print("  Test output cleaned up.")
