# Physical model and geometry

All model/persistence lengths are canonical millimeters. Inches multiply by exactly 25.4. Changing
display units does not modify stored values. z runs **DOWN from a labelled top**, matching SVG y.
Frustum top diameter is r(0)*2; bottom diameter is r(H)*2. Measurement zero is at this same top.

## Two explicit placement models

**Front-view vinyl** (default, Mote Packet 0): upright rotational surface viewed horizontally from
far enough away for orthographic projection. Desired SVG-page `(x,y)` is scaled to front-view mm:

```
x_front = center_offset + width * (x/page_width - 1/2)
z = artwork_top + height * y/page_height
theta = asin(x_front / r(z))
```

Use the visible front branch. Require `abs(x_front)/r(z) < 0.95` (persisted margin); never clamp.
Coverage also bounds theta. The entire placed page rectangle is checked conservatively at its
minimum radius; every adaptive point is checked again. Constant front y gives constant axial z.
Projecting back by `r(z)*sin(theta)` reproduces desired x. The ideal front preview is this **target**;
it does not simulate tape/strain/application behavior. Rotation rotates the resulting flat sheet,
not the object or viewing direction.

**Surface wrap / template**: x measures arc distance from the left seam on the reference circle
at axial mid-height. `theta = (x_offset + x_scaled)/r(H/2) - coverage_radians/2`.
z is still down from the labelled top. Width describes reference-circle arc width, not front-view
width. Full wrap is 360°, with two distinct seam edges in the developed sheet.

## Cylinder — exact surface development

`r = diameter/2`, circumference `2*pi*r`, slant/axial distance `s=z`.
Development is `(X,Y) = (r*theta,z)`. The front-view vinyl width for desired width W centered on the
meridian is `2*r*asin(W/(2*r))`, not W. This inverse projection is separate from development.

## Straight frustum — exact surface development

`dr = r_bottom-r_top`, axial H, slant `L=hypot(H,dr)`, `k=dr/L`, `s=z*L/H`.
For nonzero k the developed radii are `r_top/abs(k), r_bottom/abs(k)` and sector angle for angular
coverage Phi is `abs(k)*Phi`. The formula supports both taper directions.

Use a translated fan to avoid subtracting enormous apex coordinates near the cylinder limit:

```
X = r(z)*theta*sinc(k*theta)
Y = s(z) - r(z)*k*theta**2/2 * sinc(k*theta/2)**2
sinc(t) = sin(t)/t, with a small-t Taylor expansion
```

It equals `X=r*sin(k theta)/k`, `Y=s-r*(1-cos(k theta))/k`, but avoids cancellation.
As k tends to zero it smoothly becomes the cylinder formula. Principal stretches relative to the
surface metric `(r*dtheta, ds)` are 1 for both exact shapes. These claims concern **surface
development**, not laser/rotary engraving, physical vinyl behavior, or Corel interoperability.

## Measured profile — experimental continuous conformal fit

Retain raw diameter or circumference stations, measurement type, optional uncertainty and notes.
Convert D/2 or C/(2*pi) to radius once. Positive PCHIP radius interpolation has no extrapolation;
it interpolates measurement noise rather than removing it. Axial stations are not surface distances.
Split quadrature at the PCHIP knots, integrating q=sqrt(1+r_z²) and q/r themselves.

For reference z* at the middle of the placed support band, r*=r(z*), define
u(z)=integral_z*^z(q/r dz). Fit one constant for the entire carrier rectangle:

```
k = integral(w*u*log(r/r*)*q dz) / integral(w*u*u*q dz)
w = r * (asin(x_right/r) - asin(x_left/r))  # front support
R = r* * exp(k*u)
X = R*theta*sinc(k*theta)
Y_ref = r* * u*exprel(k*u) - R*k*theta²/2*sinc(k*theta/2)²
exprel(t) = expm1(t)/t; exprel(0)=1
```

The intrinsic workflow uses w=r*coverage_angle. The fit is cached by immutable profile/support
parameters, never repeated per point/strip. Degenerate denominator uses the documented local slope;
a significant |k|>1 is an error. Subtract Y_ref(z=0,theta=0) to retain Packet A's top-center anchor;
this rigid translation and the reference are recorded in export metadata.

Surface-to-flat scale is lambda=R/r in both principal directions. Required **application strain**
is 1/lambda-1: positive extension; negative compression and wrinkle risk. Extrema are found over
the support band using endpoints, knots, and polynomial stationary roots. These are numerical
geometry diagnostics, not tape/film equilibrium or approved material limits. A connected carrier
can couple letters mechanically; separate letters may need a different support/installation model.

Constant and linear-radius stations recover exact cylinder/frustum developments. Curved profiles
usually have nonzero Gaussian curvature and cannot develop unstrained. The stable k=0 limit is
X=r*theta, Y_ref=r*u. PCHIP gives a continuous C1 map, piecewise C2; contour leaves split at every
profile-knot crossing before using second-derivative bounds. Algorithm: pchip-conformal-support-fit-v1.

## Evidence and limits

All 18 independent Packet A cases (76 points) are retained as full-precision strings in
`tests/fixtures/packet-a.json`: full/partial cylinders and tapers, both directions, aggressive
arc extrema, inch/mm pairs and two near-cylinder scales. Coordinate tolerance is 1e-9 mm for
these fixtures, separate from the digital contour tolerance and physical tolerances.

Tests independently check exact metric, orientation, stable inverse/reprojection, units, template
bounds, and contour error. Projection-to-pattern magnification has singular values 1 and
(L/H)/cos(theta); it is **not material strain**. Exact development has unit material scale.
Independent sphere/catenoid belts test quadrature and opposite application-strain signs;
withheld positions check PCHIP sampling separately. Sparse symmetric stations can accidentally
match nearly quadratic truth: increasing station count is not a universal monotone error guarantee.

Exact contour derivative bounds use the supplied analytical Jacobian/Hessian. Measured-profile
bounds use analytical polynomial derivatives with numerically integrated u and fitted k. They are
not rigorous interval certificates. Measurement, profile uncertainty, actual viewing position,
material/tape, cutting calibration and installation error remain separate acceptance gates.
