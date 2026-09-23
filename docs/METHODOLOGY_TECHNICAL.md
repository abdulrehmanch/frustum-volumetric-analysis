# Volumetric Methodology (Technical)
## Contour-Based Stage–Area–Storage Analysis Using the Prismoidal Frustum Method

**Application:** Embankment, bund, levee, and terrain fill/storage volume estimation
**Vertical contour interval:** Δh = 0.5 m
**Primary volume formula:** Prismoidal (conical) frustum
**Independent cross-check:** Average End-Area

---

## 1. Objective

The objective is to convert a set of surveyed topographic contours into a schedule of
horizontal cross-sectional areas at successive elevations, and from those areas compute
the enclosed earthwork (fill) or storage volume between the base (toe) and the crest.
The result is a stage–area–storage table and the associated stage–storage curve.

The workflow rests on a single geometric idea: the solid between two adjacent contour
levels is a **frustum** — a slice bounded below and above by two parallel, horizontal
cross-sections separated by the vertical interval Δh. Summing the volumes of all such
slices from base to crest yields the total volume.

---

## 2. Coordinate Reference System

Volume and area are planar quantities and must be computed in a metric, distance-true
projection. Survey data supplied in geographic coordinates (latitude/longitude,
EPSG:4326, angular degrees) distorts both distance and area and cannot be used directly.

All geometry is therefore reprojected into a metric Universal Transverse Mercator (UTM)
zone before any measurement. The appropriate zone is selected from the dataset centroid
longitude λ:

$$
\text{Zone} = \left\lfloor \frac{\lambda + 180}{6} \right\rfloor + 1
$$

For the datasets in this study the working projection is **UTM Zone 43N (EPSG:32643)**.
After reprojection, all lengths are in metres (m) and all areas in square metres (m²).

Contour geometry carrying a Z ordinate is flattened to strictly 2D before planar
operations, so that elevation is treated as an attribute of each contour rather than as a
coordinate. This prevents the vertical component from leaking into planar area
computation.

---

## 3. Boundary and Footprint Delineation

Each contour elevation must be associated with a **closed horizontal footprint** whose
planar area A can be measured. Two situations arise:

### 3.1 Explicit boundary present
If the dataset contains an explicit outer boundary feature (an elevation-zero perimeter),
that loop defines the corridor envelope. Internal closed contour rings are nested inside
it, and each stage footprint is the region enclosed at or above that elevation.

### 3.2 No explicit boundary (open contours)
Where contours are open polylines with no enclosing perimeter, footprints are
reconstructed directly from the contour lines. For each stage elevation Z, all contour
lines at or above Z are fused into a single connected band using a **morphological close**
(an outward offset by a fixed distance followed by an equal inward offset). This bridges
the narrow gaps between adjacent contour lines into one continuous slope footprint while
leaving any large genuinely uncontoured interior excluded. The footprint therefore
represents only the surveyed contoured ground, not flat terrain the survey never covered.

### 3.3 Strict nesting
Because the set of contours at or above Z(k+1) is a subset of the set at or above Z(k),
the footprints must shrink monotonically with rising elevation:

$$
A(Z_1) \ge A(Z_2) \ge \dots \ge A(Z_{\text{crest}})
$$

This nesting is enforced explicitly by accumulating footprints downward from the crest so
that every lower stage fully contains all higher stages. The output of this step is an
ordered set of stage elevations $Z_k$ each with a measured planar area $A_k$.

---

## 4. The Prismoidal Frustum Volume

### 4.1 Geometric basis

Consider two adjacent contour stages separated by the vertical interval Δh:

```
        A_{k+1}   ── upper cross-section (higher elevation)
        ┌───────┐
       /         \
      /           \      Δh   (vertical separation between contours)
     /             \
    └───────────────┘
        A_k           ── lower cross-section (lower elevation)
```

The solid between the two cross-sections is treated as a **frustum** whose two parallel
end faces have areas $A_k$ and $A_{k+1}$. This is the generalization of a cone or pyramid
truncated by two parallel planes, and it captures the smooth taper of side slopes between
successive contours far more faithfully than a straight-sided prism.

### 4.2 Slice volume

The volume of a single frustum slice between stage k and stage k+1 is:

$$
V_{\text{slice},k} \;=\; \frac{\Delta h}{3}\left(A_k + A_{k+1} + \sqrt{A_k \, A_{k+1}}\right)
$$

where:

- $A_k$ = planar cross-sectional area at the lower stage (m²)
- $A_{k+1}$ = planar cross-sectional area at the upper stage (m²)
- $\Delta h$ = vertical interval between the two stages (m), here 0.5 m
- $\sqrt{A_k A_{k+1}}$ = the geometric mean of the two end areas, which accounts for the
  curved taper of the side walls

The term $\sqrt{A_k A_{k+1}}$ is what distinguishes the frustum formula from a simple
average of the two faces. It is exact for any solid whose cross-sectional area varies
linearly in the linear dimension (i.e., whose area varies quadratically with height),
which is the natural model for tapering embankment slopes.

### 4.3 Cumulative volume

The total volume up to any stage elevation $Z_m$ is the running sum of all slices from the
base up to that stage:

$$
V_{\text{cumul}}(Z_m) \;=\; \sum_{k=1}^{m-1} V_{\text{slice},k}
\;=\; \sum_{k=1}^{m-1} \frac{\Delta h}{3}\left(A_k + A_{k+1} + \sqrt{A_k A_{k+1}}\right)
$$

Evaluating this at the crest gives the total earthwork/storage volume. Evaluating it at
each intermediate stage produces the full **stage–storage curve**.

---

## 5. Independent Cross-Check: Average End-Area

To validate the frustum result, the same area schedule is passed through the classical
civil-engineering **Average End-Area** method, which models each slice as a straight-sided
prism whose area is the mean of its two faces:

$$
V_{\text{end-area},k} \;=\; \frac{\Delta h}{2}\left(A_k + A_{k+1}\right)
$$

$$
V_{\text{end-area,cumul}}(Z_m) \;=\; \sum_{k=1}^{m-1} \frac{\Delta h}{2}\left(A_k + A_{k+1}\right)
$$

### 5.1 Relationship between the two methods

Because the arithmetic mean is always greater than or equal to the geometric mean:

$$
\frac{A_k + A_{k+1}}{2} \;\ge\; \sqrt{A_k A_{k+1}}
$$

the Average End-Area method always returns a volume **greater than or equal to** the
frustum method. The two converge as adjacent areas become similar
($A_k \to A_{k+1}$) and diverge most where areas change sharply between stages. The
difference between them is reported per slice and in total, both in absolute (m³) and
relative (%) terms, and serves as a consistency indicator for the estimate.

---

## 6. Unit Conversions

All volumes are computed in cubic metres (m³) and additionally reported in:

- **Cubic feet:** $V_{\text{ft}^3} = V_{\text{m}^3} \times 35.31466672148859$
- **Acre-feet:** $V_{\text{acre-ft}} = V_{\text{m}^3} \times 0.000810713194$
- **Thousand cubic metres:** $V_{\text{m}^3} \div 1000$

Areas are reported in square metres (m²) and hectares ($1\ \text{ha} = 10{,}000\ \text{m}^2$).

---

## 7. Assumptions and Limitations

- Volume accuracy is bounded by contour accuracy and by the 0.5 m vertical interval; a
  finer interval reduces the residual difference between the frustum and end-area results.
- The frustum model assumes a smooth, monotonic taper of cross-sectional area between
  adjacent contours. Abrupt terrain breaks between two contour levels are approximated
  rather than resolved exactly.
- Footprints reflect only surveyed, contoured ground. Uncontoured flat terrain is
  deliberately excluded so that volume is not fabricated over ground the survey did not
  cover.
- Both methods assume the horizontal cross-sections at each stage are the true bounding
  faces of the solid; errors in footprint delineation propagate linearly into volume.

---

## 8. Summary of the Computation

| Step | Operation | Result |
|------|-----------|--------|
| 1 | Reproject to metric UTM (EPSG:32643) | Distance-true geometry |
| 2 | Delineate corridor boundary / footprints | Closed footprint per stage |
| 3 | Enforce strict nesting from crest downward | Monotonic area schedule $A_k$ |
| 4 | Frustum slice volume | $\frac{\Delta h}{3}(A_k + A_{k+1} + \sqrt{A_k A_{k+1}})$ |
| 5 | Cumulative sum base → crest | Stage–storage curve, total volume |
| 6 | Average End-Area cross-check | Upper-bound validation volume |
| 7 | Unit conversion | m³, ft³, acre-feet, hectares |
