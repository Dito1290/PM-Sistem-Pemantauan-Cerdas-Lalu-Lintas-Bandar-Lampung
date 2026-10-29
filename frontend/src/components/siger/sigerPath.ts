/**
 * Geometry of the Siger, the crown of Lampung: a crescent band carrying nine
 * leaf-shaped peaks, the centre one tallest. The band tapers to a point at
 * both ends and every peak stands inside the band, so the outline is clean
 * at any size. Everything with character on the site is cut from this shape.
 */
export const SIGER_WIDTH = 1000;
export const SIGER_HEIGHT = 600;

const PEAKS = 9;
const CENTER = SIGER_WIDTH / 2;
const TIP_X = 20; // where the crescent ends meet, at both sides
const HALF_SPAN = CENTER - TIP_X;
const TIP_Y = 300;

// Both edges of the band meet at the tips and dip in the middle.
const depth = (x: number) => 1 - ((x - CENTER) / HALF_SPAN) ** 2;
const topEdge = (x: number) => TIP_Y + 170 * depth(x);
const bottomEdge = (x: number) => TIP_Y + 292 * depth(x);

type Point = [number, number];
type Peak = { left: Point; apex: Point; right: Point; leftCtrl: Point; rightCtrl: Point };

function peaks(): Peak[] {
  const first = 100;
  const last = SIGER_WIDTH - 100;
  const spacing = (last - first) / (PEAKS - 1);
  const halfBase = spacing * 0.47;

  return Array.from({ length: PEAKS }, (_, i) => {
    const x = first + i * spacing;
    const distance = Math.abs(i - (PEAKS - 1) / 2) / ((PEAKS - 1) / 2); // 0 centre, 1 edge
    const height = 430 - distance * 230;
    // A slight outward lean that keeps every apex above its own base.
    const lean = (x - CENTER) * 0.06;
    const left: Point = [x - halfBase, topEdge(x - halfBase)];
    const right: Point = [x + halfBase, topEdge(x + halfBase)];
    const apex: Point = [x + lean, topEdge(x) - height];
    // Control points sit low and wide, so each side bulges like a leaf.
    const leftCtrl: Point = [left[0] + (apex[0] - left[0]) * 0.08, left[1] - (left[1] - apex[1]) * 0.62];
    const rightCtrl: Point = [right[0] + (apex[0] - right[0]) * 0.08, right[1] - (right[1] - apex[1]) * 0.62];
    return { left, apex, right, leftCtrl, rightCtrl };
  });
}

function build(scaleX: number, scaleY: number): string {
  const digits = scaleX === 1 ? 1 : 5;
  const p = ([x, y]: Point) => `${(x * scaleX).toFixed(digits)} ${(y * scaleY).toFixed(digits)}`;
  const along = (edge: (x: number) => number, from: number, to: number, steps: number) =>
    Array.from({ length: steps }, (_, i) => {
      const x = from + ((to - from) * (i + 1)) / steps;
      return `L ${p([x, edge(x)])}`;
    });

  const all = peaks();
  const rightTip = SIGER_WIDTH - TIP_X;
  const parts: string[] = [`M ${p([TIP_X, TIP_Y])}`];

  // Underside of the crescent, left tip to right tip.
  parts.push(...along(bottomEdge, TIP_X, rightTip, 32));

  // Top edge back to the left, rising into each peak on the way.
  parts.push(...along(topEdge, rightTip, all[PEAKS - 1].right[0], 3));
  for (const peak of [...all].reverse()) {
    parts.push(`L ${p(peak.right)}`);
    parts.push(`Q ${p(peak.rightCtrl)} ${p(peak.apex)}`);
    parts.push(`Q ${p(peak.leftCtrl)} ${p(peak.left)}`);
  }
  parts.push(...along(topEdge, all[0].left[0], TIP_X, 3));
  parts.push("Z");

  return parts.join(" ");
}

/** Path in a 1000 × 600 box, for inline SVG. */
export const sigerPath = build(1, 1);

/** Same path normalised to 0–1, for clipPathUnits="objectBoundingBox" masks. */
export const sigerPathUnit = build(1 / SIGER_WIDTH, 1 / SIGER_HEIGHT);
