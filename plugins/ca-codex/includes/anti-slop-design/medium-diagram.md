# anti-slop-design · medium: diagrams

Load for architecture, flow, sequence, and entity diagrams (Mermaid, Graphviz, ASCII, drawn). Pair
with `core`; the INDEX map also loads `color` and `layout` for this medium.

## 7.G Diagrams

- **A diagram exists to make one relationship legible.** If it does not answer a specific question
  ("how does a request flow?", "what depends on what?"), it is decoration. Name the question first.
- **Cap the node count.** Past roughly 12-15 nodes a single diagram becomes a hairball. Split by
  subsystem, collapse detail behind a labeled group, or show the slice that matters.
- **Edges carry meaning; minimize crossings.** Pick a consistent direction (top-down for hierarchy,
  left-right for a pipeline) and stick to it. Label edges when the relationship is not obvious; do not
  label every edge if direction already says it.
- **Color encodes, never decorates** (the same color-encodes-meaning discipline used for charts): use
  it for one categorical axis (layer, ownership, status), colorblind-safe, capped at a few hues. A
  rainbow of boxes is noise.
- **A legend when the encoding is not self-evident**, and consistent shapes (one shape per node kind).
- **Honest abstraction.** Do not invent components or connections to make the picture symmetric. The
  diagram is a claim about the system; a wrong box is a wrong claim (core 3.D spirit).

## Tells (diagrams)

- A hairball: too many nodes, crossing edges, no clear direction.
- Decorative multi-color boxes with no encoding meaning.
- Mixed directions / inconsistent node shapes within one diagram.
- Every edge labeled, or none labeled where the relationship is ambiguous.
- Invented boxes/links that do not exist in the real system.

## Pre-flight slice (diagrams)

- [ ] The diagram answers one named question; node count is bounded.
- [ ] Consistent direction; crossings minimized; shapes consistent.
- [ ] Color encodes a real axis (colorblind-safe) or is absent; legend where needed.
- [ ] Every box and edge maps to something real in the system.
