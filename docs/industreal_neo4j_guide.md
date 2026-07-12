# Viewing IndustReal Pipeline Results In Neo4j

This guide explains how to take the IndustReal pipeline graph outputs and view them in Neo4j.

The IndustReal Neo4j support is separate from the XR Neo4j support. This is intentional. It keeps the working XR pipeline safe, while still using comparable graph concepts such as `PipelineRun`, `Recording`, `ProcedureStep`, and `Component`.

## 1. What Gets Imported

The IndustReal pipeline creates one `assembly_graph.json` for each clip and oracle mode.

The Neo4j exporter turns those JSON files into CSV files with this graph shape:

```text
(:IndustRealRun:PipelineRun)
  -[:HAS_MODE]->
(:IndustRealMode)
  -[:HAS_CLIP]->
(:IndustRealClip:Recording)
  -[:HAS_GOAL]->
(:AssemblyGoal:CADAssemblyGoal)
  -[:TARGETS_COMPONENT]->
(:Component:IndustRealComponent)

(:AssemblyGoal:CADAssemblyGoal)
  -[:HAS_PHASE]->
(:AssemblyPhase)
  -[:HAS_STEP]->
(:AssemblyEvent:ProcedureStep)
  -[:ACTS_ON]->
(:Component:IndustRealComponent)
```

The top-level `AssemblyGoal` is grounded in the IndustReal CAD state catalog. By default it points to the final legal CAD state:

```text
state_index: 22
state_name: 11101111111
state_asset: part_geometries/state22.fbx
```

The phases are a readable grouping layer above the observed procedure steps:

```text
Initial setup
Chassis assembly
Connector installation
Bracket assembly
Wheel assembly
Correction handling
Other
```

Events inside the same clip are also linked with:

```text
(:AssemblyEvent)-[:NEXT]->(:AssemblyEvent)
```

Phases inside the same goal are linked with:

```text
(:AssemblyPhase)-[:NEXT_PHASE]->(:AssemblyPhase)
```

Final component states are linked with:

```text
(:IndustRealClip)-[:ENDS_WITH_COMPONENT_STATE]->(:Component)
```

Required CAD target components are linked with:

```text
(:AssemblyGoal)-[:TARGETS_COMPONENT]->(:Component)
```

## 2. Restore The Full Results If `/tmp` Was Cleaned

The full per-clip results normally live in `/tmp`:

```text
/tmp/industreal_pilot/results/raw_cad_dataset/raw_cad_dataset__all_test_clips/
```

If that folder is missing, restore it from the preserved bundle:

```bash
mkdir -p /tmp/industreal_pilot/results/raw_cad_dataset
tar -xzf IndustReal_Pipeline/results/preserved_tmp/raw_cad_dataset__all_test_clips.tar.gz \
  -C /tmp/industreal_pilot/results/raw_cad_dataset
```

## 3. Export Neo4j CSV Files

From the repository root, run:

```bash
python IndustReal_Pipeline/scripts/12_export_neo4j_csv.py
```

By default this reads:

```text
/tmp/industreal_pilot/results/raw_cad_dataset/raw_cad_dataset__all_test_clips/
```

and writes:

```text
IndustReal_Pipeline/results/neo4j/raw_cad_dataset__all_test_clips/
```

The generated CSV files are:

```text
nodes_runs.csv
nodes_modes.csv
nodes_clips.csv
nodes_events.csv
nodes_components.csv
nodes_goals.csv
nodes_phases.csv
edges_run_mode.csv
edges_mode_clip.csv
edges_clip_event.csv
edges_event_next.csv
edges_event_component.csv
edges_clip_final_component_state.csv
edges_clip_goal.csv
edges_goal_phase.csv
edges_goal_target_component.csv
edges_phase_step.csv
edges_phase_next.csv
```

## 4. Import Into Neo4j

Create or reuse a `.env` file with:

```text
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
```

Then run:

```bash
python IndustReal_Pipeline/scripts/13_import_neo4j.py
```

If your credentials are in the XR pipeline `.env` file, run:

```bash
python IndustReal_Pipeline/scripts/13_import_neo4j.py \
  --env-file XR_Pipeline/.env
```

The importer clears only the selected IndustReal run before importing it again. It does not delete XR nodes such as `Room`, `Object`, or XR `Event` nodes.

## 5. Useful Neo4j Browser Queries

### Count imported node types

```cypher
MATCH (n)
RETURN labels(n) AS labels, count(n) AS count
ORDER BY count DESC;
```

### List IndustReal clips

```cypher
MATCH (m:IndustRealMode)-[:HAS_CLIP]->(c:IndustRealClip)
RETURN m.name AS mode, c.archive_name AS archive, c.clip AS clip,
       c.n_frames AS frames, c.step_recall AS recall, c.step_precision AS precision
ORDER BY archive, clip, mode;
```

### Show one clip timeline

```cypher
MATCH (c:IndustRealClip {clip: "03_assy_1_3", mode: "od_plus_psr_error_hints"})
      -[:HAS_STEP]->(e:AssemblyEvent)
RETURN e.frame AS frame, e.time_s AS time_s, e.event_type AS type,
       e.component AS component, e.action_desc AS description
ORDER BY e.frame, e.local_event_id;
```

### Show the CAD-grounded assembly goal

```cypher
MATCH (c:IndustRealClip {clip: "03_assy_0_1", mode: "od_plus_psr_error_hints"})
      -[:HAS_GOAL]->(g:AssemblyGoal)
RETURN g.goal_name AS goal,
       g.target_state_index AS target_state,
       g.target_state_name AS state_bits,
       g.target_state_asset AS cad_asset,
       g.target_components AS target_components;
```

### Show the CAD goal and required target components

```cypher
MATCH path = (c:IndustRealClip {clip: "03_assy_0_1", mode: "od_plus_psr_error_hints"})
      -[:HAS_GOAL]->(:AssemblyGoal)
      -[:TARGETS_COMPONENT]->(:Component)
RETURN path;
```

### Show phases under the CAD goal

```cypher
MATCH (c:IndustRealClip {clip: "03_assy_0_1", mode: "od_plus_psr_error_hints"})
      -[:HAS_GOAL]->(g:AssemblyGoal)
      -[:HAS_PHASE]->(p:AssemblyPhase)
RETURN g.goal_name AS goal, p.phase_order AS order, p.phase_name AS phase,
       p.step_count AS steps, p.first_frame AS first_frame,
       p.last_frame AS last_frame, p.has_error AS has_error
ORDER BY p.phase_order;
```

### Show the goal-to-step graph

```cypher
MATCH path = (c:IndustRealClip {clip: "03_assy_0_1", mode: "od_plus_psr_error_hints"})
      -[:HAS_GOAL]->(:AssemblyGoal)
      -[:HAS_PHASE]->(:AssemblyPhase)
      -[:HAS_STEP]->(:AssemblyEvent)
RETURN path;
```

### Show the goal, phases, steps, and acted-on components

```cypher
MATCH path = (c:IndustRealClip {clip: "03_assy_0_1", mode: "od_plus_psr_error_hints"})
      -[:HAS_GOAL]->(:AssemblyGoal)
      -[:HAS_PHASE]->(:AssemblyPhase)
      -[:HAS_STEP]->(:AssemblyEvent)
      -[:ACTS_ON]->(:Component)
RETURN path;
```

### Check whether the final clip state reached the CAD goal

```cypher
MATCH (c:IndustRealClip {clip: "03_assy_0_1", mode: "od_plus_psr_error_hints"})
      -[:HAS_GOAL]->(g:AssemblyGoal)
MATCH (g)-[:TARGETS_COMPONENT]->(target:Component)
OPTIONAL MATCH (c)-[state:ENDS_WITH_COMPONENT_STATE]->(target)
WITH c, g, collect({
       component: target.name,
       required: true,
       final_state: coalesce(state.state, "missing")
     }) AS component_status,
     collect(coalesce(state.state, "missing")) AS final_states
RETURN c.name AS clip,
       g.name AS goal,
       component_status,
       all(final_state IN final_states WHERE final_state = "installed") AS reached_cad_goal;
```

### Show the timeline as a graph

```cypher
MATCH (c:IndustRealClip {clip: "03_assy_1_3", mode: "od_plus_psr_error_hints"})
      -[:HAS_STEP]->(first:AssemblyEvent)
WHERE NOT (:AssemblyEvent)-[:NEXT]->(first)
MATCH path = (first)-[:NEXT*0..30]->(:AssemblyEvent)
RETURN path
LIMIT 1;
```

### Show all error events

```cypher
MATCH (e:AssemblyEvent {event_type: "ERROR"})
RETURN e.mode AS mode, e.archive_name AS archive, e.clip AS clip,
       e.frame AS frame, e.component AS component, e.action_desc AS description
ORDER BY archive, clip, frame;
```

### Compare the two oracle modes by event count

```cypher
MATCH (m:IndustRealMode)-[:HAS_CLIP]->(c:IndustRealClip)-[:HAS_STEP]->(e:AssemblyEvent)
RETURN m.name AS mode, count(e) AS predicted_events
ORDER BY mode;
```

### See which components are involved most often

```cypher
MATCH (e:AssemblyEvent)-[:ACTS_ON]->(c:Component)
RETURN c.name AS component, count(e) AS event_count
ORDER BY event_count DESC;
```

### Compare step recall by mode

```cypher
MATCH (m:IndustRealMode)-[:HAS_CLIP]->(c:IndustRealClip)
RETURN m.name AS mode, avg(c.step_recall) AS mean_recall,
       avg(c.step_precision) AS mean_precision
ORDER BY mode;
```

## 6. How To Explain This In A Presentation

A good plain-language explanation is:

```text
The IndustReal pipeline creates assembly graph JSON files. We added a Neo4j bridge that converts those graph files into a database graph. In Neo4j, each run contains modes, each mode contains clips, each clip contains procedure steps, and each step acts on a component. This makes it possible to query timelines, errors, components, and compare the two oracle modes visually.
```

With the CAD-grounded goal layer, you can now explain it as:

```text
The graph has a top-level final CAD assembly goal. Under that goal, observed steps are grouped into readable assembly phases such as chassis assembly, connector installation, wheel assembly, and correction handling. This makes the graph closer to the assembly-graph idea in the thesis: a final operation goal with lower-level steps and components underneath it.
```

The complete assembly evidence view adds one more idea:

```text
The CAD goal now points directly to the components required by the final CAD state. The observed steps point to the components the operator acted on, and the clip points to the final known component states. This makes it possible to query whether the observed procedure reached the CAD-defined target, instead of only showing that steps happened.
```

The important caveat is:

```text
This graph uses CAD symbolically as the final target state and component structure. It does not prove image-only detection or metric 3D CAD alignment.
```
