# NX MCP Server Assessment and NXOpen Roadmap

This project currently runs without Siemens NX by opting tests into
`nx_mcp.testing.mock_nxopen` through `NX_MCP_USE_MOCK_NXOPEN=1`.
Production code should import Siemens' real `NXOpen` module through
`nx_mcp.nxopen.load_nxopen()`.

## Current State

The MCP framework is in place:

- MCP JSON-RPC server in `src/nx_mcp/server.py`.
- Optional HTTP wrapper in `src/nx_mcp/http_server.py`.
- Tool registry and response wrappers.
- NX session wrapper in `src/nx_mcp/nx_session.py`.
- File, sketch, modeling, assembly, measurement, and utility tools.
- Mock-based unit tests that do not require Siemens NX.

This is a good MCP prototype, but it is not yet a real Siemens NX automation
server. Most NX behavior is still represented by mock-friendly placeholder
logic.

## Import Boundary

- Keep all real NXOpen imports behind `nx_mcp.nxopen`.
- Do not add a top-level `NXOpen.py` file under `src`; that shadows Siemens'
  real module on `PYTHONPATH`.
- The fake NXOpen module has already been moved to
  `src/nx_mcp/testing/mock_nxopen.py`.
- Unit tests must explicitly opt into the fake module with
  `NX_MCP_USE_MOCK_NXOPEN=1`.
- Add integration tests separately from unit tests once Siemens NX is available.

## Priorities After Installing NX

### 1. Verify NXOpen Access

Determine whether `import NXOpen` works:

- In normal Python.
- Only inside NX Python.
- Through a bridge process.

This is the most important step because it determines the runtime architecture.

### 2. Choose Architecture

Option A: MCP inside NX.

- Direct access.
- Harder integration and process management.

Option B: external MCP plus NX bridge.

- Recommended starting point if normal Python cannot import NXOpen reliably.
- Cleaner MCP integration.
- Keeps the MCP server independent from NX process lifetime.

Option C: external Python plus NXOpen.

- Simple if supported by the installed NX environment.
- Can be fragile across NX/Python versions and environment setup.

### 3. Make Session Handling Real

Add:

- NX running checks.
- Work/display part handling.
- Undo marks around tool operations.
- Builder cleanup guarantees.
- NX-specific error translation.

### 4. Replace Placeholder Tools

Convert modeling, sketch, assembly, and measurement tools to use:

- Real object lookup.
- Real NX builders.
- Proper geometry and component selection.
- Commit/cleanup workflows.
- Structured result data.

### 5. Improve MCP Responses

Instead of returning only text content built from `str(result)`, return
structured payloads:

```json
{
  "ok": true,
  "message": "...",
  "data": {}
}
```

### 6. Add Missing HTTP Dependencies

If HTTP mode remains, add runtime dependencies for:

- `fastapi`
- `uvicorn`

### 7. Testing Strategy

Keep three test layers:

- Mock unit tests without Siemens NX.
- NX integration tests for real NXOpen calls.
- End-to-end workflows through an MCP client.

## Milestones

1. Install NX and verify how `NXOpen` can be imported.
2. Create/open/save a part successfully with real NXOpen.
3. Choose and document the runtime architecture.
4. Implement real sketch creation.
5. Build a rectangle -> sketch -> extrude -> save workflow.
6. Add object lookup for bodies, faces, edges, features, sketches, and
   components.
7. Upgrade modeling tools.
8. Add real measurements.
9. Configure and test an MCP client.

## Tool TODOs

- `file_ops.create_part`: replace `Parts.NewDisplay` placeholder arguments with
  the real NX file-new workflow, template selection, units, and display part
  handling.
- `file_ops.open_part`: handle NX open status objects, failed loads, and part
  display/work-part switching.
- `file_ops.save_part`: capture and report NX save status, modified parts, and
  read-only file errors.
- `file_ops.export_step`: configure real STEP creator options, object selection,
  destination path validation, commit status, and cleanup.
- `file_ops.export_stl`: configure real STL creator tolerances, selected bodies,
  binary/text output, commit status, and cleanup.
- `sketch.create_sketch`: create an actual sketch builder, resolve XY/XZ/YZ
  datum planes, set origin/orientation, commit, and make it active.
- `sketch.draw_line`: create lines in the active sketch or work part using real
  curve APIs and update the sketch.
- `sketch.draw_rectangle`: build four real line curves with constraints or
  dimensions when sketch mode is active.
- `sketch.draw_circle`: create a real circle/arc object with NX units and sketch
  association.
- `sketch.draw_arc`: create a real bounded arc with validated angle direction
  and sketch association.
- `modeling.extrude`: select the active sketch/profile, set start/end limits,
  boolean mode, direction, and commit a real feature.
- `modeling.revolve`: resolve the requested axis into a real NX axis or datum,
  select a section, set angular limits, and commit a real feature.
- `modeling.boolean_unite`: resolve named bodies, set target/tool bodies, apply
  NX boolean options, and report the committed feature.
- `modeling.boolean_subtract`: resolve target/tool bodies, set subtraction
  options, and report the committed feature.
- `modeling.add_fillet`: resolve edge selections, set radius law/tolerance, and
  commit a real edge blend.
- `modeling.add_chamfer`: resolve edge selections, set offset mode and values,
  and commit a real chamfer.
- `modeling.add_hole`: create a positioned hole feature with placement plane,
  diameter, depth, direction, and through/blind options.
- `modeling.mirror_feature`: resolve a feature by name, resolve mirror plane,
  and commit a real mirror feature.
- `modeling.pattern_feature`: resolve feature and direction, configure count and
  pitch expressions, and commit a real linear pattern.
- `assembly.add_component`: use the real add-component builder with component
  path, reference set, transform/origin, load options, and error handling.
- `assembly.list_components`: traverse the real root component tree recursively
  and return stable names/paths.
- `assembly.mate_components`: resolve components and faces, create the requested
  real assembly constraint, and solve/report constraint status.
- `assembly.reposition_component`: resolve the component, apply a real transform
  or positioning network move, and update assembly constraints if needed.
- `measure.measure_distance`: replace pure point math with NX measurement when
  measuring selected objects, while keeping point-to-point math as a utility.
- `measure.measure_angle`: replace pure vector math with NX measurement when
  measuring selected edges/faces, while keeping vector math as a utility.
- `measure.measure_volume`: query mass properties for selected bodies or the
  work part instead of using box dimensions.
- `measure.get_bounding_box`: use NX bounding box APIs for selected bodies or
  the work part and return min/max coordinates.
- `utility.set_view`: map supported names to real NX view orientations and
  update the active modeling view.
- `utility.fit_view`: call the real work-view fit API and handle no-display-part
  cases.
- `utility.take_screenshot`: use the real NX image export API with path,
  dimensions, and overwrite handling.
- `utility.list_features`: enumerate real part features, names, types,
  suppression state, and timestamps if available.
