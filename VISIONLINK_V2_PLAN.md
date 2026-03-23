# VisionLink V2 — Full Build Plan

## Purpose

Build V2 as a **persistent object memory system** on top of the current live YOLO tracking app.

The current app already does:
- live camera streaming
- YOLO-based object detection
- temporary tracking IDs
- overlay rendering on the phone

V2 should add:
- clear full-frame snapshot capture
- clean object crops from frozen full images
- per-object descriptor extraction
- persistent object identities across time
- object memory storage
- multi-cue matching
- crop quality filtering and cleanup
- audit/debug reports explaining why objects matched or did not match

## Core principle

**Live tracking is for responsiveness.**
**Snapshots are for memory and identity.**

Do **not** learn long-term object memory from moving live tracking boxes.
Only update persistent object memory from **clear full-frame snapshots**.

---

## 1. V2 Goals

### Primary goals
1. Capture a clear full-frame image.
2. Detect all objects in that frozen image.
3. Crop each object from the full image.
4. Extract useful descriptors from each crop.
5. Match each crop to a persistent object memory entry.
6. Assign or reuse a persistent `object_uid`.
7. Update memory only with high-quality evidence.
8. Preserve full auditability of every match decision.

### Secondary goals
1. Allow later user naming/correction of objects.
2. Support custom household objects not covered by YOLO classes.
3. Reduce false matches between nearby objects.
4. Keep the architecture extensible for:
   - segmentation masks later
   - OCR improvements later
   - room mapping / SLAM later
   - ROS2 later if needed

### Non-goals for V2
Do **not** make these core dependencies yet:
- full SLAM
- ROS2 bridge
- WebRTC transport rewrite
- custom detector training as a requirement
- segmentation-first redesign

These can plug in later.

---

## 2. High-Level Architecture

V2 should have two lanes.

### Lane A — Live perception lane
Purpose:
- low-latency user feedback
- temporary track continuity
- phone overlay

This lane keeps the current system:
- phone camera feed
- laptop receives frames
- YOLO detection
- tracker
- overlay and debug UI

Output of this lane:
- temporary `track_id`
- current detection label/confidence
- bbox/centroid
- live preview only

This lane is **not** the source of truth for memory.

### Lane B — Snapshot memory lane
Purpose:
- accurate crop extraction
- descriptor extraction
- persistent identity assignment
- memory updates

This lane should:
1. receive a full snapshot
2. run detection on the still frame
3. crop all objects from the full image
4. score crop quality
5. reject junk crops
6. extract descriptors from accepted crops
7. compare to object memory
8. assign persistent `object_uid`
9. update memory only when evidence is strong enough

---

## 3. Identity Model

V2 must clearly separate these three concepts.

### A. Live track identity
Short-term, frame-to-frame only.

Field:
- `track_id`

Used for:
- current overlay
- short-term continuity while visible

This can change.

### B. Persistent object identity
Long-term identity of the real physical object.

Field:
- `object_uid`

Used for:
- memory
- retrieval
- object history
- user labeling
- future re-identification

This should survive across snapshots and sessions.

### C. Semantic label
What the system or user thinks the object is.

Fields:
- `detector_label`
- `semantic_label`
- `user_label`

Example:
- `detector_label = "suitcase"`
- `semantic_label = "storage box"`
- `user_label = "laundry box"`

These must not be conflated.

---

## 4. V2 Modules

### 4.1 Snapshot Manager
Responsibilities:
- trigger snapshot capture
- save full-resolution frame
- save snapshot metadata
- assign `snapshot_id`
- store timestamp and session context

Inputs:
- live frame stream
- manual SNAP trigger for now

Outputs:
- saved full image
- `snapshot_id`
- snapshot metadata record

### 4.2 Snapshot Detector
Responsibilities:
- run object detection on the frozen full image
- return all detections for that snapshot
- use rectangle boxes initially
- preserve optional path for masks later

Inputs:
- full snapshot image

Outputs:
- detection list: bbox, class, confidence

Use:
- existing YOLO path
- keep this separate from live tracking output

### 4.3 Crop Extractor
Responsibilities:
- crop each detected object from the saved full image
- optionally add a configurable margin
- reject edge-clipped or invalid crops
- save crop image files

Inputs:
- full snapshot image
- detection bboxes

Outputs:
- object crop files
- crop metadata

Important:
- crops must come from the still full image, not live tracking boxes

### 4.4 Crop Quality Scorer
Responsibilities:
- score each crop for memory usefulness
- reject junk
- decide whether crop is memory-worthy

Quality checks:
- blur / sharpness
- crop size
- detector confidence
- edge clipping
- occlusion overlap if available
- extreme aspect ratio
- duplicate redundancy against same-snapshot neighbors

Outputs:
- `quality_score`
- `accept_for_memory`
- `rejection_reasons`

### 4.5 Descriptor Extractor
Responsibilities:
- compute object descriptors for accepted crops

Start with:
- embedding vector
- color descriptor
- shape descriptor
- bbox size / normalized size
- detector label/confidence
- blur score
- OCR tokens when useful
- snapshot context fields
- zone placeholder if available
- neighbor relation context if available

Do not overbuild first version. Start with durable features.

### 4.6 Object Memory Store
Responsibilities:
- persist stable memory for known/provisional objects
- store exemplars
- store descriptor summaries
- maintain object metadata

Needs:
- object records
- exemplar references
- descriptor index
- update rules
- cleanup rules

### 4.7 Identity Matcher
Responsibilities:
- retrieve candidate objects from memory
- compute multi-cue match scores
- decide: known match / ambiguous / new object

Must produce a **score breakdown** for auditing.

### 4.8 Memory Updater
Responsibilities:
- merge accepted evidence into existing object memory
- create provisional objects for new items
- avoid polluting memory with weak evidence
- retain only best exemplars

### 4.9 Cleanup / Maintenance Engine
Responsibilities:
- remove low-value provisional junk
- cap exemplars per object
- down-rank contradictory weak matches
- identify possible duplicate object memories for review

### 4.10 Audit / Report Generator
Responsibilities:
- generate detailed explainable reports for every snapshot and object match

Must log:
- why crop was accepted/rejected
- candidate objects considered
- per-cue scores
- final match decision
- memory updates performed
- ambiguity warnings
- duplicate warnings

### 4.11 Review / Relabel Workflow
Responsibilities:
- inspect object memories later
- rename objects
- add aliases
- merge duplicates manually
- reject junk memories

Can start with exportable JSON and folders. No polished UI required yet.

---

## 5. Data Flow

1. **Live mode** — phone streams as now; live detection/tracking/overlay unchanged
2. **Snapshot trigger** — SNAP pressed; full frame saved with `snapshot_id`
3. **Snapshot detection** — run YOLO on frozen full image
4. **Crop extraction** — crop every object from saved full image
5. **Crop quality scoring** — accept/reject each crop; rejected crops stay in logs but skip memory
6. **Descriptor extraction** — embedding, color, shape, OCR, context
7. **Candidate retrieval** — top-K nearest from embedding index
8. **Multi-cue match scoring** — per-candidate score breakdown
9. **Identity decision** — `known_match` / `ambiguous` / `new_object`
10. **Memory update** — update known, create provisional, or log ambiguous
11. **Audit output** — snapshot report + per-object decision report

---

## 6. Matching Strategy

### Candidate retrieval
Use embedding similarity first to narrow memory candidates.
Then run detailed scoring on a small candidate set.

### Match cues

**Strong:**
- embedding similarity
- OCR token match when present
- room/zone agreement when available
- relation agreement when available

**Medium:**
- color similarity
- shape similarity
- size consistency
- detector-label consistency

**Weak:**
- material estimate
- detector class alone

### Match outcomes
- `same_known_object`
- `ambiguous_candidate`
- `new_object`

Do not force uncertain merges. Wrong merge is worse than delayed merge.

---

## 7. Object Categories

### Rigid objects
Examples: toilet, sink, bottle, appliance, box, chair, plant pot
Use: embedding, color, shape, OCR, location context, relations
These are the easiest.

### Soft / deformable objects
Examples: clothing, towels, blankets
Use: color/pattern, texture descriptors, zone context, weaker thresholds
Do not over-merge — shape changes.

### Flat / image-bearing objects
Examples: posters, photos, framed art, labels
Use: OCR, image embedding, rectangular/flat cues, wall/zone location
Strong when text or graphics are visible.

This category concept should be built into the architecture even if lightly used in V2.

---

## 8. Quality Filtering and Cleanup

### Reject or down-rank crops if:
- blurry
- too small
- detector confidence too low
- object clipped by frame edge
- heavily occluded
- redundant duplicate of a stronger crop
- contradictory weak unknown

### Promote crops if:
- sharp
- large enough
- centered
- strong confidence
- distinct viewpoint
- useful text visible
- new view not already represented in exemplars

### Exemplar policy
Keep a limited set of best exemplars per object (configurable cap, e.g. 5–20).
Choose based on: sharpness, viewpoint diversity, crop quality, distinctiveness, OCR usefulness.

---

## 9. Storage Layout

```text
project_root/
  snapshots/
    snap_000001/
      full.jpg
      snapshot_meta.json
      detections.json
      crops/
        det_0001.jpg
        det_0002.jpg
      crop_analysis.json
      match_report.json

  objects/
    obj_000001/
      object_memory.json
      exemplars/
        ex_0001.jpg
        ex_0002.jpg
      evidence/
        ev_000123.json
        ev_000456.json

  indexes/
    embedding_index.faiss
    embedding_map.json

  reports/
    daily/
    failed_matches/
    ambiguous/
```

Each crop links back to: source snapshot, bbox in full image, quality score, assigned object UID.

---

## 10. Schemas

### 10.1 Snapshot record
- `snapshot_id`, timestamp, source frame metadata, full image path
- detection list, accepted crop IDs, rejected crop IDs, summary report path

### 10.2 Crop evidence record
- `crop_id`, `snapshot_id`, image path, bbox
- detector label, detector confidence
- quality score, blur score
- embedding reference or vector path
- color descriptor, shape descriptor, OCR tokens
- provisional/known object assignment, match decision, candidate scores

### 10.3 Object memory record
- `object_uid`
- status: `provisional` / `stable` / `named` / `ambiguous`
- category type: `rigid` / `soft` / `flat` / `unknown`
- detector labels seen, semantic label, user label, aliases
- exemplar image paths, embedding summary / exemplar references
- color summary, shape summary, OCR token history
- zone history, relation history
- times seen, first seen, last seen
- confidence score, notes / flags

---

## 11. Software to Use vs Code to Write

### Use existing libraries
- current YOLO stack for detection
- embedding model library (e.g. CLIP, torchvision) for image embeddings
- FAISS or equivalent for nearest-neighbor retrieval
- OCR library only when needed

### Write custom code for
- snapshot manager
- crop extraction from full snapshots
- crop quality scoring
- descriptor extraction orchestration
- object memory schema and updates
- multi-cue identity matcher
- ambiguity logic
- exemplar selection logic
- cleanup policy
- audit/report generation
- review/relabel export hooks

The glue and memory logic are the real product.

---

## 12. Auditability Requirements

For every object decision, log:
- crop quality scores and accept/reject outcome
- candidate memory objects considered
- per-cue score breakdown
- final decision and threshold path
- whether memory was updated
- whether a new object was created
- whether ambiguity was raised

Required report types:
- per-snapshot summary
- per-object match report
- ambiguous object report
- duplicate candidate report
- provisional object aging report

This audit layer is mandatory so V2 can be improved safely.

---

## 13. Testing Plan

### Unit tests
- crop extraction correctness
- quality scoring behavior
- descriptor extraction schema validation
- matcher scoring path
- object memory update logic
- exemplar pruning logic

### Integration tests
- snapshot → detections → crops → descriptors → retrieval → match → memory update
- repeated snapshots of same object reuse same `object_uid`
- poor crops rejected from memory updates
- ambiguous cases stay ambiguous
- nearby similar objects do not incorrectly merge

### Regression tests
Fixed snapshot test set from your house:
- same object from multiple views
- two similar objects side-by-side
- soft/deformable object cases
- poster/photo cases
- blurry snapshot cases
- occluded object cases

Measure: false merge rate, false split rate, new-object overcreation rate, crop rejection quality, audit completeness.

---

## 14. Phasing

### V2 Phase 1 — Core object memory
snapshot manager, snapshot detector, crop extractor, crop quality scoring, basic object memory store, embedding retrieval, identity matcher, audit logs

### V2 Phase 2 — Better descriptors and cleanup
color descriptor, shape descriptor, exemplar selection, provisional object cleanup, ambiguity handling improvements, duplicate memory reports

### V2 Phase 3 — Context and review
object category types, room zones, nearby object relation storage, relabel/export workflow, manual merge/reject tools

---

## 15. Future Extensions (Design for Them Now, Do Not Require Them Yet)

### Segmentation masks
- detection record can later hold mask data
- crop extractor should be mask-ready

### SLAM / world coordinates
- reserve fields for zone/world pose
- keep context layer modular

### ROS2 bridge
- stable internal schemas
- event-style outputs

### IMU fusion
- allow snapshot metadata to store motion state later

---

## 16. What Not to Do

1. Do not use live moving tracking boxes as memory crops.
2. Do not merge object identity based on detector label alone.
3. Do not store every crop forever.
4. Do not overwrite strong exemplars with worse evidence.
5. Do not force uncertain matches.
6. Do not make V2 depend on full SLAM or ROS2 to be useful.
7. Do not build a black-box matcher with no audit output.
8. Do not assume soft objects can be matched the same way as rigid objects.

---

## 17. Definition of Success for V2

V2 is successful if it can:
1. take a full clear snapshot
2. detect and crop all major objects from that snapshot
3. reject poor-quality crops
4. create persistent object memories
5. re-identify the same real household object across multiple snapshots
6. avoid obvious false merges between neighboring objects
7. allow later naming/correction of custom household items
8. explain every match decision through logs/reports

---

## 18. Final Instruction to the Next AI

Build V2 as a **persistent object memory engine**, not just a tracker upgrade.

The correct mental model:
- live lane = fast perception
- snapshot lane = accurate memory
- `track_id` = temporary
- `object_uid` = persistent
- each crop = evidence
- object memory = curated record of the best evidence
- matching must be multi-cue and auditable
- uncertain matches must remain ambiguous, not forced

Prioritize durable architecture over throwaway hacks.
Do not overbuild infrastructure that is not yet required.
Do build the core memory, matching, cleanup, and audit systems in a way that will survive future SLAM, segmentation, and robotics integration.
