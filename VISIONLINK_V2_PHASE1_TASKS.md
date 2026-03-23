# VisionLink V2 — Phase 1 Tasks

## Goal

Build the first working version of the V2 object-memory system without breaking the existing live YOLO tracking pipeline.

Phase 1 focuses on:
- clear full-frame snapshot capture
- object detection on frozen snapshots
- cropping objects from the full image
- crop quality scoring
- persistent object memory storage
- embedding-based candidate retrieval
- first-pass identity matching
- audit/debug logs

This phase does **not** include:
- SLAM
- ROS 2 bridge
- WebRTC changes
- segmentation-first redesign
- full custom labeling UI
- full room/world mapping

---

## Core rules

1. **Live tracking remains for responsiveness only** — keep current YOLO tracking and overlay path working
2. **Do not learn from moving tracking boxes** — object memory updates must come from full still-frame snapshots only
3. **Keep identities separate** — `track_id` = temporary live ID, `object_uid` = persistent object memory ID
4. **Every match must be auditable** — log why each crop was accepted/rejected and why each object matched or did not match
5. **Do not force uncertain merges** — outcomes must allow: known match, ambiguous candidate, new object

---

## Phase 1 deliverables

### A. Snapshot pipeline
- [ ] Add a snapshot manager that saves a full-frame image from the live stream
- [ ] Assign each snapshot a unique `snapshot_id`
- [ ] Save snapshot metadata (`timestamp`, source info, image path, etc.)
- [ ] Ensure snapshots are stored separately from live debug data

### B. Snapshot detection path
- [ ] Add a dedicated snapshot detection path using the current YOLO detector
- [ ] Run detection on the frozen full-resolution snapshot image
- [ ] Save the detection list for each snapshot
- [ ] Keep this path separate from live tracking outputs

### C. Crop extraction
- [ ] Crop every detected object directly from the saved full image
- [ ] Support configurable crop padding/margin
- [ ] Reject invalid crops (zero area, out-of-bounds, badly clipped)
- [ ] Save crop files under the snapshot folder
- [ ] Save crop metadata including bbox, class, confidence, source snapshot

### D. Crop quality scoring
- [ ] Implement blur/sharpness scoring
- [ ] Implement minimum crop size checks
- [ ] Implement detector-confidence gating
- [ ] Implement edge-clipping detection
- [ ] Return: `quality_score`, `accept_for_memory`, `rejection_reasons`
- [ ] Store all crop quality results in a per-snapshot analysis file

### E. Object memory store
- [ ] Create persistent `object_uid` generation
- [ ] Create durable on-disk storage for object records
- [ ] Create object record schema with at least:
  - `object_uid`
  - `status` (`provisional`, `stable`, `named`, `ambiguous`)
  - `detector_labels_seen`
  - `semantic_label`
  - `user_label`
  - `times_seen`
  - `first_seen`
  - `last_seen`
  - `exemplar_paths`
  - links to evidence records
- [ ] Keep object records inspectable in JSON form

### F. Descriptor extraction
- [ ] Add embedding extraction for accepted crops
- [ ] Store embedding references or vectors in a consistent location
- [ ] Add basic color descriptor extraction
- [ ] Add basic shape descriptor extraction
- [ ] Store per-crop descriptor records
- [ ] Keep descriptor extraction modular so more features can be added later

### G. Embedding retrieval
- [ ] Add a vector index for object-memory retrieval
- [ ] Support top-K nearest candidate search from new crop embeddings
- [ ] Maintain a mapping between embedding entries and `object_uid`
- [ ] Ensure index updates when new stable object evidence is added

### H. Identity matcher
- [ ] Build first-pass identity matching using:
  - embedding similarity
  - color similarity
  - shape similarity
  - detector-label consistency (weak cue)
- [ ] Return one of: `known_match`, `ambiguous_candidate`, `new_object`
- [ ] Do not force low-confidence merges
- [ ] Log score breakdown per candidate

### I. Memory update logic
- [ ] If `known_match`, update the matched object record
- [ ] If `new_object`, create a new provisional object record
- [ ] If `ambiguous_candidate`, log ambiguity and avoid forced merge
- [ ] Add exemplar-selection logic: keep only good exemplars, do not replace stronger exemplars with worse crops
- [ ] Keep the initial exemplar policy simple but explicit

### J. Audit/reporting
- [ ] Write a per-snapshot report file summarizing:
  - detections, crops created, crops accepted/rejected, candidate matches, final match outcomes
- [ ] Write per-crop match reports showing:
  - crop quality results, descriptor summary, candidate object scores, final decision
- [ ] Write error/warning logs for:
  - ambiguous matches, poor crop quality, duplicate-like candidates, failed descriptor extraction
- [ ] Keep reports human-readable

---

## Suggested repo additions

### New modules (under `laptop-server/app/memory/`)
- [ ] `snapshot_manager.py`
- [ ] `snapshot_detector.py`
- [ ] `crop_extractor.py`
- [ ] `crop_quality.py`
- [ ] `descriptor_extractor.py`
- [ ] `object_memory_store.py`
- [ ] `embedding_index.py`
- [ ] `identity_matcher.py`
- [ ] `memory_updater.py`
- [ ] `audit_reporter.py`

### Storage layout
- [ ] `memory_data/snapshots/`
- [ ] `memory_data/objects/`
- [ ] `memory_data/indexes/`
- [ ] `memory_data/reports/`

---

## Reuse vs preserve

### Reuse
- [ ] Existing YOLO detector infrastructure where possible
- [ ] Existing live streaming pipeline
- [ ] Existing live tracker / overlay path
- [ ] Existing snapshot trigger if already present and usable

### Preserve untouched
- [ ] Live phone overlay behavior
- [ ] Current live detection responsiveness
- [ ] V1's working baseline behavior on branch `main`

### Do not over-couple
- [ ] Do not tightly couple memory logic to live overlay rendering
- [ ] Do not bake snapshot memory assumptions into the live tracker path
- [ ] Do not make persistent object memory dependent on current `track_id`

---

## Phase 1 test requirements

### Unit tests
- [ ] crop extraction correctness
- [ ] crop quality scoring behavior
- [ ] descriptor extraction schema validation
- [ ] object record creation/update logic
- [ ] identity matcher decision path
- [ ] exemplar selection behavior

### Integration tests
- [ ] snapshot → detection → crops → descriptors → retrieval → match → memory update
- [ ] repeated snapshots of same object reuse the same `object_uid`
- [ ] low-quality crops are rejected from memory updates
- [ ] obviously different objects do not merge too easily
- [ ] ambiguous cases remain ambiguous

### Manual validation tests
- [ ] same household object across multiple snapshots gets reused correctly
- [ ] nearby similar objects do not immediately collapse into one object
- [ ] poor blurry snapshot does not pollute memory
- [ ] reports are inspectable and explain decisions clearly

---

## Success criteria for Phase 1

Phase 1 is complete when the system can:

- [ ] save a full snapshot
- [ ] detect objects in the frozen snapshot
- [ ] crop objects from the full image
- [ ] reject poor-quality crops
- [ ] compute descriptors for good crops
- [ ] search object memory for likely matches
- [ ] assign or create persistent `object_uid`
- [ ] avoid forcing uncertain matches
- [ ] update object memory records
- [ ] generate useful audit/debug reports

---

## Explicit non-goals for Phase 1

Do **not** add these yet:
- [ ] SLAM
- [ ] world-coordinate anchoring
- [ ] ROS 2 bridge
- [ ] WebRTC transport replacement
- [ ] segmentation masks as a hard dependency
- [ ] custom detector training
- [ ] polished review GUI
- [ ] aggressive auto-merging of ambiguous objects

---

## Instruction to the coding AI

Before implementing:
- inspect the current V1 repo structure
- map existing modules to these Phase 1 tasks
- identify what can be reused vs what should be isolated
- propose exact file/module changes
- call out likely integration risks
- then implement Phase 1 in a way that keeps the architecture extensible for later V2 phases
