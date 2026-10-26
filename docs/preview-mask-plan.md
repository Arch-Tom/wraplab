# Interactive preview and mask planning implementation

Baseline: `a0dc157c655edbf064024b7493e6a0625e446d97`, the latest available
SVG-corrected descendant of the framing fixes and four-group research. The original
local checkout at `14a15c5` is preserved. Feature branch:
`codex/interactive-3d-mask-planning`. Initial work was local only. Subsequent source
publication is separately authorized; packaging and production approval remain excluded.

1. Record fresh native tests and deterministic export hashes before editing production code.
2. Add a versioned scene adapter around the existing surface/model, normalized SVG and
   compensation APIs. The pinned Essentials wheel already includes native Qt OpenGL: use
   depth-tested, smoothly shaded triangles and normalized-SVG textures, with no browser,
   CDN or extra dependency. Keep the existing 2D view as the renderer-failure fallback.
3. Add authenticated, topology-checked component assignments, exactly three CantorLand masks
   (star, both Hebrew rows, English). Keep global splitting and experimental group fits explicit.
   Carry object-space registration separately from flat coordinates and cutter paths.
4. Add deterministic mask output as a separate, transactional operation. Ordinary exports
   stay on the unchanged exporter. References are separate and explicitly DO NOT CUT.
5. Persist conservative preview/planner options with old project loading retained; validate
   mappings, topology, serialization, unchanged hashes, failure paths and native interactions.

Historical measurements are reconstruction inputs until a newer saved customer project is
identified. Never extrapolate the measured bell, substitute fonts, center the star, treat
four independently fitted groups as three sheets, or claim material/Corel acceptance.
