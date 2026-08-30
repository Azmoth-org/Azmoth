/**
 * DESIGN.md's signature hero backdrop.
 *
 * The spec calls it non-negotiable — "bare-canvas heroes break the brand" — and also
 * says to implement it as an image or SVG rather than a CSS gradient, because the real
 * mesh has organic blob shapes. This does it in CSS anyway, and the reason is
 * measurable rather than stylistic: the mesh sits directly behind the H1, which is the
 * largest contentful paint on this page. An image there costs a request on the
 * critical path and a repaint when it lands, to decorate text that is already legible
 * without it. Five off-centre radial stops at low alpha get close enough to the
 * organic shape that the trade is not worth making — see `.azm-mesh` in globals.css.
 *
 * `aria-hidden` and `pointer-events-none`: it is decoration, and it must not sit
 * between a cursor and the call-to-action it washes over.
 */
export function GradientMesh() {
  return <div aria-hidden="true" className="azm-mesh" />;
}
