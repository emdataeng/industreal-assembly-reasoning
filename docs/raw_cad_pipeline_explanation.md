# Raw CAD-Grounded IndustReal Pipeline, Explained Simply

This document explains the IndustReal work in this repository from the beginning, assuming the reader has no prior knowledge of the dataset or the pipeline.

The short version is:

We built a separate IndustReal pipeline that can read raw IndustReal recordings, use the dataset's own assembly-state labels as a trusted "oracle", apply CAD-informed assembly rules, convert those states into procedure steps, build graph outputs, and evaluate the results over the real IndustReal test clips.

This is not yet a pipeline that detects every part from raw images by itself. The current thesis-facing version is deliberately "oracle-first": it asks, "If the dataset already tells us the assembly state, can our CAD/rule-based reasoning turn that into useful procedural understanding?"

## 1. Why This Pipeline Exists

The original XR pipeline was built around your own Quest captures, especially `session_003`.

That XR workflow uses your captured data and produces structured outputs such as manifests, object reasoning, procedure steps, and graph-like assembly understanding.

The IndustReal work has a different purpose:

- Test whether the same general idea can transfer to an external industrial dataset.
- Avoid depending on your own Quest recordings only.
- Use IndustReal's assembly labels and CAD-related knowledge to produce procedure understanding.
- Run on much more data than the small pilot, while staying safe with storage limits.

The important thesis idea is:

If we have reliable information about assembly states, then CAD-informed rules and legal assembly constraints can help transform low-level frame labels into higher-level procedure understanding.

## 2. Important Vocabulary

This section explains the main terms in plain language.

| Term | Simple meaning |
| --- | --- |
| Clip | One recorded assembly attempt from IndustReal. Think of it as one video recording with metadata. |
| Frame | One moment/image inside a clip. The dataset is treated as 10 frames per second. |
| RGB | Normal color image. |
| Depth | A depth-looking image from the recording. In this pipeline it is kept for inspection, but not used as reliable metric 3D. |
| Stereo left/right | Two additional camera images from left and right sensors. Kept for inspection. |
| Pose | Where the headset/camera was estimated to be at a frame. |
| OD labels | IndustReal labels that describe the assembly state at certain frames. In this pipeline these are used as trusted state labels. |
| PSR labels | Procedure Step Recognition labels. These describe assembly steps such as installing or removing parts. |
| CAD | Computer-Aided Design. In this branch it means symbolic assembly knowledge, not 3D alignment. |
| Oracle | A trusted source of information from the dataset. Here it mainly means using `OD_labels.json` instead of trying to detect states from images. |
| State | The current assembly condition, for example which parts are installed. |
| Step | A procedure action inferred from state changes, for example "Install front chassis". |
| EGG / assembly graph | A graph-style representation of the predicted assembly procedure. |

## 3. What "CAD" Means Here

The dataset does include real CAD files.

In this repository, those CAD files are stored here:

```text
IndustReal_Pipeline/data/part_geometries.zip
```

That archive contains CAD-related assets, including `.fbx` files, `.3mf` files, and an overview PDF. Examples include state models and part geometry files.

However, the current pipeline does not use the CAD models as 3D objects that are aligned onto the camera images.

That would require trustworthy camera calibration, especially exact camera intrinsics. Camera intrinsics tell us how pixels relate to real 3D rays. Without them, using CAD for metric 6D pose estimation would be risky.

So in this pipeline, CAD is used symbolically.

That means CAD helps define:

| CAD-informed thing | What it means in easy words |
| --- | --- |
| Part vocabulary | The official list of parts we care about. |
| Component names | Stable names such as `base`, `front chassis`, and `rear wheel assembly`. |
| Legal assembly states | Which combinations of parts are valid during the assembly. |
| Legal transitions | Which state changes are allowed, for example moving from one assembly stage to the next. |
| Detector phrases | Fixed phrases that could later be used by an image detector. |

So the current CAD usage is like a rulebook:

"These are the parts, these are the legal states, and these are the state transitions that make sense."

It is not yet:

"Place this exact 3D CAD model into this RGB-D frame and estimate its 3D pose."

## 4. Why We Use an Oracle First

At first, we planned to use image detection on raw RGB frames.

That would mean asking a detector such as Grounding DINO to find parts in the images.

But your thesis goal here is not to prove that we can build the best possible object detector. The more relevant question is:

If the dataset gives us trustworthy assembly-state labels, can our pipeline reason from those labels into steps, errors, and graphs?

That is why the current main path is `oracle_od`.

`oracle_od` means:

Use the labels that already come with IndustReal instead of trying to detect the state from scratch.

This saves time and keeps the thesis focused on assembly reasoning instead of detector tuning.

## 5. The Two Oracle Modes

The full dataset runner processes each clip in two modes.

### Mode 1: `od_only`

This mode uses only `OD_labels.json`.

It answers:

"How much can we recover from IndustReal assembly-state labels alone?"

This is the cleaner baseline because it does not use explicit procedure error hints.

### Mode 2: `od_plus_psr_error_hints`

This mode uses `OD_labels.json` plus explicit error moments from `PSR_labels_with_errors.csv`.

It answers:

"What improves if the pipeline also knows the labeled error moments?"

This is the stronger thesis-facing mode because it better represents a supervised reasoning setup where known error events can be used.

## 6. IndustReal Dataset Structure Used by This Pipeline

The real dataset is large, so the batch pipeline does not extract everything permanently into the repo.

Instead, it reads test archives such as:

```text
test_p1.zip
test_p2.zip
test_p3.zip
```

Inside each archive there are clip folders. Each clip folder contains image streams plus metadata files.

A typical clip looks like this conceptually:

```text
03_assy_0_1/
  rgb/
    000000.jpg
    000001.jpg
    ...
  depth/
    000000.jpg
    000001.jpg
    ...
  stereo_left/
    000000.jpg
    000001.jpg
    ...
  stereo_right/
    000000.jpg
    000001.jpg
    ...
  pose.csv
  gaze.csv
  hands.csv
  OD_labels.json
  PSR_labels.csv
  PSR_labels_with_errors.csv
  PSR_labels_raw.csv
  AR_labels.csv
```

The full real run confirmed that all 19 processed test clips had the expected four image streams and the expected metadata files.

## 7. What Each Dataset File Is Used For

| Dataset file/folder | What it contains | How this pipeline uses it |
| --- | --- | --- |
| `rgb/` | Color images | Used for manifest completeness and debug visuals. Not the main oracle signal. |
| `depth/` | Depth-like JPG images | Stored and visualized, but marked as `non_metric_jpg`. Not used for metric 3D. |
| `stereo_left/` | Left stereo images | Stored and visualized for inspection. |
| `stereo_right/` | Right stereo images | Stored and visualized for inspection. |
| `pose.csv` | Camera/headset pose vectors | Converted into 4x4 pose matrices in the manifest. |
| `gaze.csv` | Eye gaze data | Added to the manifest when available. |
| `hands.csv` | Hand-tracking information | Used to mark whether hands are present. |
| `OD_labels.json` | Assembly-state labels | Main oracle input for state reasoning. |
| `PSR_labels.csv` | Procedure step labels | Used as ground truth for step evaluation. |
| `PSR_labels_with_errors.csv` | Procedure labels including mistakes/errors | Used for error hints in the stronger oracle mode and for error evaluation. |
| `PSR_labels_raw.csv` | Raw procedure labels | Preserved as metadata. |
| `AR_labels.csv` | Additional annotation metadata | Preserved as metadata. |

## 8. The Real Full-Dataset Scope

The latest real batch run processed all configured test clips from:

```text
test_p1
test_p2
test_p3
```

The run covered 19 clips:

| Archive | Clips |
| --- | --- |
| `test_p1` | `03_assy_0_1`, `03_assy_1_3`, `08_assy_0_1`, `08_assy_2_4`, `09_assy_0_1`, `09_assy_3_1` |
| `test_p2` | `10_assy_0_1`, `10_assy_3_2`, `12_assy_0_1`, `12_assy_3_4`, `13_assy_0_1` |
| `test_p3` | `17_assy_0_1`, `17_assy_1_5`, `18_assy_0_1`, `18_assy_2_5`, `19_assy_0_1`, `19_assy_3_5`, `23_assy_0_1`, `23_assy_1_2` |

Total frames processed:

```text
65,838 frames
```

Shortest clip:

```text
2,586 frames
```

Longest clip:

```text
5,276 frames
```

Because the data is large, the pipeline extracts and processes one clip at a time instead of unpacking the whole dataset permanently.

## 9. Storage Strategy

This is important because IndustReal is too large to casually keep inside the repo or codespace.

The pipeline separates temporary heavy data from durable lightweight reports.

### Temporary data

Full per-clip outputs and extracted working data go under:

```text
/tmp/industreal_pilot/
```

Files in `/tmp` are useful while the codespace is alive, but they are not guaranteed to survive if the codespace is closed or cleaned.

### Durable repo reports

Small summaries and reports are saved inside the repository:

```text
IndustReal_Pipeline/results/raw_cad_dataset_reports/raw_cad_dataset__all_test_clips/
```

This folder contains the important durable result files:

```text
summary.csv
mode_comparison.csv
run_manifest.json
clip_inventory.csv
failure_log.json
```

### Preserved full result bundle

A compressed copy of the full `/tmp` result outputs was also preserved here:

```text
IndustReal_Pipeline/results/preserved_tmp/raw_cad_dataset__all_test_clips.tar.gz
```

This helps protect the work if `/tmp` disappears.

## 10. Main Config Files

### Pilot config

```text
IndustReal_Pipeline/configs/raw_cad_pilot.json
```

This is for the smaller pilot workflow.

It uses selected clips and event-centered slices.

### Full dataset config

```text
IndustReal_Pipeline/configs/raw_cad_dataset.json
```

This is the main config for the full real-data batch run.

It defines:

- Which archives to process.
- Whether missing archives may be downloaded.
- Which oracle modes to run.
- Where temporary outputs go.
- Where durable reports go.
- Whether resume mode is enabled.

The full dataset config is separate from the pilot config on purpose, so the small pilot workflow and the full batch workflow do not conflict.

## 11. Main Scripts

This section explains the scripts in the order a beginner should understand them.

### `scripts/01_run_demo.py`

This is the older demo path.

It uses precomputed ASD/PSR-style results rather than the new raw IndustReal batch path.

It was intentionally left unchanged so the old baseline still works.

### `scripts/02_prepare_raw_pilot.py`

This prepares a small pilot slice.

The pilot slice is useful for debugging because it extracts only selected windows around important events.

This is not the main full-dataset runner.

### `scripts/03_build_raw_manifest.py`

This builds a manifest for the small pilot.

A manifest is a table where each row describes one frame and points to its RGB, depth, stereo, pose, gaze, and hand data.

### `scripts/04_visualize_raw_pilot.py`

This creates debug images for the pilot.

It helps verify that the extracted frames and labels line up correctly.

### `scripts/05_build_cad_catalog.py`

This builds the CAD-informed part and state catalogs.

It turns part names, state definitions, and CAD asset references into machine-readable JSON files.

### `scripts/06_run_raw_detector.py`

This runs the detector/evidence stage for the pilot.

In the current thesis branch, the important detector path is the oracle path, not the open-vocabulary image detector.

### `scripts/07_infer_cad_states.py`

This infers assembly states for the pilot using CAD-informed rules and evidence.

### `scripts/08_export_raw_psr_egg.py`

This converts inferred states into procedure steps and graph outputs for the pilot.

### `scripts/11_run_oracle_dataset_batch.py`

This is the main full-dataset entrypoint.

It runs the full real IndustReal test set clip by clip.

It performs:

1. Archive discovery.
2. Clip inventory creation.
3. Clip extraction into `/tmp`.
4. Raw manifest creation.
5. Oracle evidence creation.
6. State sequence creation.
7. Direct state-to-step conversion.
8. Graph export.
9. Evaluation.
10. Aggregate report generation.

This is the script to use for whole-dataset oracle runs.

### `scripts/16_run_layer4_validation.py`

This runs thesis Layer 4 step validation over the Layer 3 reasoning outputs.

It reads:

- `step_records.jsonl`
- `predicates.jsonl`
- `inferred_constraints.csv`
- `config/thesis_rules.yaml`

The `--config` flag points to the thesis reasoning config. Layer 4 uses the `validation` block in that config for the acceptance and uncertainty thresholds:

```json
"validation": {
  "tau_acc": 0.70,
  "tau_unc": 0.35
}
```

Example command:

```bash
python scripts/16_run_layer4_validation.py \
  --step-records results/reasoning_layers/raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1/step_records.jsonl \
  --predicates results/reasoning_layers/raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1/predicates.jsonl \
  --constraints results/reasoning_layers/raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1/inferred_constraints.csv \
  --output results/reasoning_layers/raw_cad_dataset__all_test_clips__sample_test_p1_03_assy_0_1/validation_records.jsonl \
  --config config/thesis_rules.yaml
```

It writes:

- `validation_records.jsonl`
- `step_validations.csv`
- `explanation_traces.json`

## 12. Main Source Modules

The scripts above are thin entrypoints. Most real logic lives in `IndustReal_Pipeline/src/`.

### `src/dataset_batch.py`

This is the orchestrator for the full dataset.

It is responsible for:

- Finding archives.
- Optionally downloading missing archives if allowed.
- Listing clips inside archives.
- Extracting one clip at a time.
- Running both oracle modes.
- Writing per-clip outputs.
- Updating the resume ledger.
- Writing `summary.csv`.
- Writing `mode_comparison.csv`.
- Writing `failure_log.json`.

This is the heart of the full-dataset runner.

### `src/raw_loader.py`

This reads raw IndustReal clip folders.

It discovers:

- RGB frames.
- Depth frames.
- Stereo frames.
- Pose rows.
- Gaze rows.
- Hand rows.
- OD labels.
- PSR labels.

It gives the rest of the pipeline a consistent way to access the raw clip.

### `src/hl2_pose.py`

This converts IndustReal/HoloLens-style pose data into 4x4 camera pose matrices.

The input pose data has fields such as:

- `forward`
- `position`
- `up`

The module turns those into a standard transformation matrix with 16 numbers:

```text
pose_00 ... pose_15
```

One real clip, `test_p3/17_assy_1_5`, had three all-zero pose rows. The code handles this by reusing the nearest valid pose instead of crashing.

### `src/raw_manifest.py`

This builds `raw_manifest.csv`.

Each row represents one frame.

Important columns include:

- `clip`
- `slice_order`
- `frame_idx`
- `frame_name`
- `timestamp_ns`
- `rgb_path`
- `depth_path`
- `stereo_left_path`
- `stereo_right_path`
- `gaze_x`
- `gaze_y`
- `has_hands`
- `source_archive`
- `split`
- `notes`
- `pose_00` through `pose_15`

The timestamp is created from the frame number:

```text
timestamp_ns = frame_idx * 100,000,000
```

That means the pipeline treats the recording as 10 frames per second.

### `src/raw_viz.py`

This creates debug visualizations.

Examples include:

- RGB sample images.
- RGB and depth side-by-side previews.
- Stereo previews.
- Gaze overlays.
- Camera trajectory plots.

These visuals are for checking data quality and alignment. They are not the main thesis output.

### `src/cad_catalog.py`

This builds the CAD-informed catalogs.

It creates:

```text
cad_part_catalog.json
cad_state_catalog.json
```

`cad_part_catalog.json` defines the canonical component list and related vocabulary.

`cad_state_catalog.json` defines legal assembly states and legal state transitions.

### `src/detector_rgb.py`

Despite the name, the important current path is not a real RGB detector.

The main path is `oracle_od`.

It reads `OD_labels.json` and converts the labels into the evidence format expected downstream.

It can also add explicit error information from `PSR_labels_with_errors.csv` in the stronger mode.

The open-vocabulary image detector path exists as optional future work, but it is not the current reported result.

### `src/track2d.py`

This smooths frame evidence over time.

For real object detections, this would help link detections across adjacent frames.

For the oracle path, it mainly keeps the same output contract as a detector-based system would use.

### `src/cad_reasoner.py`

This is the assembly reasoning module.

It takes the oracle evidence and creates a frame-by-frame state timeline.

It also converts state changes into procedure steps.

Important behavior:

- Before the first observed label, it seeds the timeline with the first known state.
- Between labels, it carries the previous state forward.
- When a later label changes state, the transition is placed at that later labeled frame.
- Error hints can inject explicit `error_state` moments.
- It avoids inventing install steps for parts that were already present before the current timeline began.

### `src/eval_raw_cad.py`

This evaluates the predicted outputs.

It computes:

- State accuracy.
- Step precision.
- Step recall.
- Median step delay in frames.
- Error-window recall.
- Legal state rate.

### `src/psr.py`

This is older Procedure Step Recognition logic.

The current oracle-first path keeps its older B3-style output as a diagnostic comparison artifact:

```text
psr_pred_b3_diagnostic.json
```

But the main output is now direct state-to-step conversion:

```text
psr_pred.json
```

### `src/egg_builder.py`

This builds graph-style assembly outputs from predicted procedure steps.

The output is:

```text
assembly_graph.json
```

This is the closest current equivalent to creating a knowledge graph from the IndustReal data.

## 13. Pipeline Flow From Raw Clip to Result

Here is the full flow in simple terms:

```text
IndustReal test archive
  -> find clip folders
  -> extract one clip into /tmp
  -> build raw_manifest.csv
  -> read OD_labels.json and PSR labels
  -> create oracle evidence
  -> create state_sequence.csv
  -> convert state changes into procedure steps
  -> build assembly_graph.json
  -> compute metrics.json
  -> add one row to summary.csv
```

The same clip is processed twice:

```text
mode 1: od_only
mode 2: od_plus_psr_error_hints
```

This lets us compare:

- What OD labels alone can do.
- What improves when explicit error labels are also used.

## 14. Output Files for Each Clip and Mode

For each clip and oracle mode, the batch runner writes outputs like this under `/tmp`:

```text
/tmp/industreal_pilot/results/raw_cad_dataset/raw_cad_dataset__all_test_clips/
  modes/
    od_only/
      test_p1/
        03_assy_0_1/
          raw_manifest.csv
          frame_evidence.jsonl
          smoothed_frame_evidence.jsonl
          state_sequence.csv
          psr_pred.json
          psr_pred_b3_diagnostic.json
          gt_steps.json
          assembly_graph.json
          metrics.json
          debug_visuals/
    od_plus_psr_error_hints/
      test_p1/
        03_assy_0_1/
          ...
```

### `raw_manifest.csv`

This is the frame index.

It tells the pipeline:

- Which frame number this is.
- Where the RGB image is.
- Where the depth image is.
- Where stereo images are.
- What pose belongs to the frame.
- Whether gaze/hands data exists.

### `frame_evidence.jsonl`

This is the first evidence file.

In the oracle path, it contains evidence created from dataset labels.

One line corresponds to one frame.

### `smoothed_frame_evidence.jsonl`

This is the cleaned/smoothed evidence file.

It is the evidence handed into the state reasoner.

### `state_sequence.csv`

This is the frame-by-frame assembly-state timeline.

It says:

"At this frame, the assembly is in this state."

It also includes flags that explain where the state came from:

- Seeded initial state.
- Directly observed state label.
- Carried-forward state.
- Inferred error state.

### `psr_pred.json`

This is the main predicted procedure-step output.

It is built directly from state transitions.

Example idea:

If the state changes from "base only" to "base plus front chassis", the pipeline predicts an install step for the front chassis.

### `psr_pred_b3_diagnostic.json`

This is the older PSR-style diagnostic output.

It is kept for comparison, but it is not the main thesis-facing output.

### `gt_steps.json`

This is the ground-truth step list for the full clip.

It is used to evaluate predicted steps.

### `assembly_graph.json`

This is the graph representation of the predicted procedure.

It turns predicted steps into graph nodes and relationships.

This is the current IndustReal graph/knowledge-graph-like output.

### `metrics.json`

This stores evaluation metrics for one clip and one oracle mode.

## 15. Durable Report Files

The most important result files are preserved in:

```text
IndustReal_Pipeline/results/raw_cad_dataset_reports/raw_cad_dataset__all_test_clips/
```

### `summary.csv`

One row per clip per mode.

Because we processed 19 clips and 2 modes, it has:

```text
38 rows
```

It includes:

- Archive name.
- Clip name.
- Mode name.
- Number of frames.
- State accuracy.
- Predicted step count.
- Ground-truth step count.
- Step precision.
- Step recall.
- Median step delay.
- Error-window recall.
- Legal state rate.

### `mode_comparison.csv`

This compares the two modes.

It includes per-clip comparisons and overall rows.

This is the easiest file to use when explaining:

"Does adding error hints improve the oracle pipeline?"

### `run_manifest.json`

This is the run ledger.

It records what clip/mode pairs completed.

The final real run completed:

```text
38 clip/mode jobs
```

### `clip_inventory.csv`

This lists the real clips found in the archives.

It confirms that each clip had the expected streams and metadata.

### `failure_log.json`

This records failures.

For the latest full real run:

```text
0 failures
```

## 16. Final Real-Data Results

The full test batch processed:

```text
19 clips
2 oracle modes per clip
38 total clip/mode jobs
65,838 total frames
0 failures
```

### Overall comparison

| Metric | `od_only` | `od_plus_psr_error_hints` |
| --- | ---: | ---: |
| Mean step recall | 0.794 | 0.981 |
| Mean step precision | 0.373 | 0.437 |
| Total predicted steps | 313 | 346 |
| Total ground-truth steps | 187 | 187 |
| Clips with perfect step recall | 5 / 19 | 16 / 19 |
| Error clips successfully handled | 0 / 11 | 11 / 11 |
| Failures | 0 | 0 |

### What step recall means

Step recall answers:

"Of the real assembly steps that happened, how many did the pipeline recover?"

A recall of 1.0 means the pipeline found all ground-truth steps for that clip.

The stronger mode had mean recall around:

```text
0.981
```

That means it recovered almost all labeled steps across the real test clips.

### What step precision means

Step precision answers:

"Of the steps the pipeline predicted, how many matched real labeled steps?"

Precision is lower than recall in both modes.

That means the pipeline tends to predict extra steps.

In simple terms:

The current pipeline is very good at not missing important steps, especially in the stronger mode, but it still sometimes says that extra steps happened.

### What error-window recall means

Error-window recall answers:

"When the dataset says an error happened, did the pipeline catch an error around that moment?"

There were 11 clips with explicit error windows.

In the stronger mode:

```text
11 / 11 error clips were caught
```

So among clips that actually have labeled error windows, the stronger mode reached:

```text
100% error-window recall
```

One nuance:

The overall row in `mode_comparison.csv` reports an error-window value around `0.579` because it averages over all 19 clips, including clips that do not contain error windows. For explanation purposes, the more intuitive statement is:

"Among the 11 clips that contained labeled errors, the stronger mode caught all 11."

## 17. What The Results Mean

The most important conclusion is:

The pipeline is now working end to end on real IndustReal test data.

It can:

- Read real IndustReal clips.
- Build frame manifests.
- Use IndustReal state labels as oracle input.
- Apply CAD-informed state and transition rules.
- Convert state changes into procedure steps.
- Inject and recover labeled error moments in the stronger mode.
- Build graph outputs.
- Evaluate results across the full configured test set.
- Produce durable summary reports.

This is a meaningful result because it shows that the idea is not limited to your own XR captures.

It also shows that symbolic CAD/rule-based reasoning can turn assembly labels into higher-level procedure understanding.

## 18. What The Results Do Not Prove Yet

It is equally important to be honest about what this does not prove.

The current results do not prove that the pipeline can detect all parts directly from raw RGB-D images.

Why?

Because the thesis-facing path uses the dataset's labels as oracle input.

The current results also do not prove metric CAD alignment.

Why?

Because the pipeline does not place 3D CAD models into the camera frames.

The current CAD contribution is symbolic:

- Part names.
- Legal states.
- Legal transitions.
- Assembly rules.
- Vocabulary.

That is still useful, but it is different from full 3D CAD tracking.

## 19. Are We Creating a Knowledge Graph?

Yes, in a practical sense.

The file:

```text
assembly_graph.json
```

is the current graph output.

It represents the assembly procedure as structured graph data built from predicted steps.

It is not yet a large semantic knowledge graph with ontology tooling, SPARQL, or RDF.

But it is a graph-style procedural representation:

- Steps become structured entities.
- Assembly order is preserved.
- Error/correction behavior can be represented.
- Outputs can be compared across clips.

So the safest explanation is:

"The pipeline creates assembly graph outputs from IndustReal procedure predictions. These are knowledge-graph-like outputs, but not yet a formal RDF/ontology knowledge graph."

## 20. Why The Pipeline Uses Full Clips For Batch Runs

The original pilot used small event-centered slices.

That was useful for early testing because it reduced storage and runtime.

For the full-dataset run, we changed to full clips.

This matters because:

- Full clips avoid confusion caused by starting in the middle of an assembly.
- Evaluation can use all ground-truth steps in the clip.
- Error handling can be measured across complete recordings.
- The result is more thesis-ready than a tiny slice.

## 21. How To Rerun The Full Dataset Batch

From the repository root:

```bash
python IndustReal_Pipeline/scripts/11_run_oracle_dataset_batch.py \
  --config IndustReal_Pipeline/configs/raw_cad_dataset.json
```

If the archives are missing from local storage and downloading is allowed:

```bash
python IndustReal_Pipeline/scripts/11_run_oracle_dataset_batch.py \
  --config IndustReal_Pipeline/configs/raw_cad_dataset.json \
  --download-missing
```

To rerun a specific archive or clip:

```bash
python IndustReal_Pipeline/scripts/11_run_oracle_dataset_batch.py \
  --config IndustReal_Pipeline/configs/raw_cad_dataset.json \
  --archives test_p3 \
  --clips 17_assy_1_5
```

The runner supports resume mode, so completed clip/mode jobs can be skipped on later runs.

## 22. How To Restore Preserved Full Outputs

If `/tmp` is cleaned but the preserved tarball still exists, restore the full result bundle like this:

```bash
mkdir -p /tmp/industreal_pilot/results/raw_cad_dataset
tar -xzf IndustReal_Pipeline/results/preserved_tmp/raw_cad_dataset__all_test_clips.tar.gz \
  -C /tmp/industreal_pilot/results/raw_cad_dataset
```

After that, the per-clip full outputs should again be available under:

```text
/tmp/industreal_pilot/results/raw_cad_dataset/raw_cad_dataset__all_test_clips/
```

## 23. Recommended Way To Present This Work

A simple presentation explanation could be:

"We adapted the XR assembly-understanding idea to IndustReal. Because IndustReal is large, we created a batch runner that processes one clip at a time in temporary storage. Instead of focusing on object detection, we used IndustReal's own assembly-state labels as an oracle. Then we used CAD-informed assembly knowledge: known parts, legal states, and legal transitions, to convert frame-level states into procedure steps and graph outputs. On 19 real test clips, the stronger oracle mode recovered almost all ground-truth steps and caught all labeled error clips."

Then explain the limitation:

"This does not yet prove image-only detection or 3D CAD alignment. It proves the reasoning layer: given trustworthy assembly-state labels, the pipeline can produce useful procedural and graph-level understanding."

## 24. Best Next Improvements

The next improvements should be chosen based on thesis priority.

### Best next step for thesis reporting

Create tables and figures from:

```text
summary.csv
mode_comparison.csv
assembly_graph.json
```

This will make the results easier to present.

### Best next step for improving quality

Reduce extra predicted steps to improve precision.

Recall is already strong in the `od_plus_psr_error_hints` mode, but precision is still modest.

This means the next technical improvement should focus on preventing duplicate or unnecessary predicted steps.

### Best next step for CAD depth

Investigate whether the real CAD files can be used more deeply.

Possible future work:

- Visualize CAD model states beside predicted procedure graphs.
- Map graph nodes more explicitly to CAD assets.
- Add non-metric CAD diagrams to reports.
- Only attempt metric CAD alignment if reliable intrinsics are found.

### Best next step for scaling

If running more archives becomes slow or storage-heavy, move the batch runner to UPPMAX or another larger machine.

The code was designed so that the same output contracts can work locally or on a larger compute environment.

## 25. Final Verdict

The build is successful as an oracle-first IndustReal reasoning pipeline.

It now runs on the real configured IndustReal test clips, not only synthetic fixtures and not only the small pilot.

The strongest result is:

```text
od_plus_psr_error_hints recovered nearly all procedure steps and caught all labeled error clips.
```

The main weakness is:

```text
precision is still low because the pipeline predicts extra steps.
```

The honest thesis framing is:

"This pipeline demonstrates CAD-informed procedural reasoning over IndustReal using trusted dataset labels. It does not yet demonstrate fully automatic image-based part detection or metric 3D CAD alignment."

