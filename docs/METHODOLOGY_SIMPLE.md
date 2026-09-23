# How We Calculate the Volume (Plain-Language Guide)

This note explains, in everyday terms, how we work out how much material an embankment or
bund holds — or how much water a basin can store — starting from a survey map of contour
lines. No maths background is needed.

---

## What we start with

A survey gives us **contour lines**. A contour line joins all the points on the ground
that sit at the same height, like the height markings on a walking map. Lines close
together mean a steep slope; lines far apart mean gentle ground.

Each contour in our data sits 0.5 metres in height above the one below it. So the survey
is really a stack of level slices through the structure, half a metre apart.

---

## The main idea: slicing the shape like a cake

Imagine the embankment as a layered cake. If you slice it horizontally every half metre,
you get a stack of thin layers. If you can measure the volume of each layer and add them
all up, you get the total volume of the whole thing.

That is exactly what we do:

1. **Measure the footprint at each height.** For every contour line, we work out the area
   of ground it encloses — the size of that horizontal slice, measured in square metres.
2. **Find the volume of each layer** between one contour and the next.
3. **Add all the layers together**, from the bottom up, to get the total.

---

## Measuring the area correctly

Before measuring anything, we convert the map from latitude-and-longitude (which is fine
for showing a location but distorts real distances) into a proper metric map where every
metre on the ground is a true metre on the page. Only then are the areas and volumes
accurate.

We also make sure each slice sits neatly inside the one below it. As you go higher up the
structure it gets narrower, so each higher slice must be smaller than the one beneath it.
We only count ground that the survey actually contoured, so we never invent volume over
flat, unsurveyed land.

---

## Working out the volume of one layer

Here is the part that needs a little care. Each layer is not a simple box. Its bottom face
is a bit wider than its top face, because the sides of an embankment slope inwards as they
rise. So a layer looks more like a slightly tapered slab than a flat brick.

```
      smaller top
      ┌───────┐
     /         \      <- sloping sides
    /           \
   └─────────────┘
    larger bottom
```

If we simply treated each layer as a box, we would slightly overstate the volume. Instead
we use a shape called a **frustum** — the proper name for a slice with a wider bottom and a
narrower top and sloping sides. It matches the real shape of an embankment layer much more
closely, so the volume we get for each layer is more realistic.

For each layer we only need three things: the area of its bottom face, the area of its top
face, and the fixed 0.5-metre height between them. From those, we calculate the layer's
true tapered volume.

---

## Adding it all up

Once every layer has a volume, we add them together from the base to the top. Two useful
numbers come out of this:

- The **total volume** of the whole structure.
- A **running total** at each height — how much volume has built up by the time you reach
  each contour. Plotted on a chart, this becomes the "stage–storage curve", which shows at
  a glance how volume grows as the structure gets taller (or how storage grows as a basin
  fills).

---

## Double-checking the answer

To be confident in the result, we calculate the volume a **second way** using a simpler,
long-established surveying method that treats each layer as a plain average slab. This
simpler method always gives a slightly larger number than the tapered-slice method, so the
two results naturally bracket the true value. When the two numbers come out close to each
other, we know the estimate is sound. We report both, along with the small difference
between them, as a built-in sanity check.

---

## What you get at the end

- The total volume, given in cubic metres and also in cubic feet and acre-feet so it can be
  read in whichever units suit the project.
- The area and volume at every half-metre step, laid out in a simple table.
- A chart showing how volume builds up with height.

In short: we slice the structure into thin half-metre layers, measure each layer as a
realistically tapered shape rather than a plain box, add them all up, and confirm the total
with an independent second calculation.
