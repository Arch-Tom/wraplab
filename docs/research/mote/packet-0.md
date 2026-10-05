# Packet 0 — GO WITH CONSTRAINTS

Received through Tom's authorized research handoff. Distilled technical content:

- Actual job: cut vinyl on an axisymmetric bell; lettering should look level and undistorted
  from a straight-on view. Generic wrap placement is insufficient.
- Desired front-view point `(x,y)` maps to `z = z_anchor + y`,
  `theta = asin(x/r(z))` on the visible front branch, for an explicitly assumed upright
  bell and distant horizontal orthographic view.
- Canonical axial position is down from a labelled top, matching SVG y-down.
- Require a margin from `abs(x) = r(z)`. Reject invalid coordinates; never clamp them.
- Exact cylinder/frustum development; general curved bell flattening requires strain or cuts.
- Report pattern stretch/compression separately from ideal front appearance.
- Vinyl properties, transfer tape, connected mask vs separate letters, and actual viewing
  distance remain unconfirmed. Neither preview nor SVG tests constitute physical approval.

Sources supplied by Mote:

- https://web.mit.edu/hyperbook/Patrikalakis-Maekawa-Cho/node190.html
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.PchipInterpolator.html

Further geometry fixtures and SVG contracts are expected, not yet received.
