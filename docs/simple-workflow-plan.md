# Simple workflow implementation plan

Baseline: `30c539a55410d7015df0360616f3fe8d3521266b`, native Windows Python 3.12.10 / Qt 6.8.3.
Branch: `codex/wraplab-simple-workflow`. Main, RC4 and the integration reference are preserved.

1. Keep all geometry, domain, adaptive SVG conversion, persistence and original fixtures intact.
2. Introduce an operator workspace builder over the existing MainWindow callbacks. Make object
   measurements, SVG import, proportional sizing and top-referenced placement the main controls.
   Present Cylinder, Tapered object and Custom curved object without changing their model values.
3. Show On the Object and Flat Cutting Pattern together. Label schematic/profile and front-view
   targets honestly; keep Original Artwork secondary. Preserve aspect-correct fit, zoom and pan.
   Use accurate numeric placement and Center; dragging pans the view and does not move artwork.
4. Keep Export Compensated SVG visible in a fixed footer. Default to artwork only; progressively
   disclose guide/template/comparison export, rotation, production tolerance, presets and notes.
5. Preserve mode/unit/model semantics. Make loading/invalid/stale states explicit, provide next-step
   feedback and physical export dimensions. Keep project/recovery/preset formats and atomic saves.
6. Separate XML syntax diagnostics from blocked XML constructs. Accept only an explicitly proven
   transparent root-page background; continue rejecting other unknown/geometry-affecting styles.
   Use synthetic Corel-like fixtures and do not claim repair of missing original user SVGs.
7. Establish fresh original tests, compare reference engine exports, run the complete revised suite
   and native source workflows for cylinder/taper/measured objects, inspect empty/populated/error
   layouts and resizing/scaling, then commit locally. No packaging, policy changes or remote writes.

Full over-280-character source smoke remains separate from ordinary operation on this host with
Windows long-path support disabled. CorelDRAW and physical material acceptance remain unverified.
