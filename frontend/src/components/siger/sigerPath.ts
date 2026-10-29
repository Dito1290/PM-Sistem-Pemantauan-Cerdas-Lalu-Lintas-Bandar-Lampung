/**
 * Geometry of the Siger, the crown of Lampung: a thick curved band carrying
 * nine leaf-shaped peaks, the centre one tallest, the outer ones leaning out.
 * Everything with character on the site is cut from this one shape.
 */
export const SIGER_WIDTH = 1000;
export const SIGER_HEIGHT = 600;

const PEAKS = 9;
const CENTER = SIGER_WIDTH / 2;

// Top and bottom edges of the band: curves that dip in the middle.
const topEdge = (x: number) => 300 + 170 * (1 - ((x - CENTER) / 470) ** 2);
const bottomEdge = (x: number) => 360 + 232 * (1 - ((x - CENTER) / 500) ** 2);

type Point = [number, number];

type Peak = { left: Point; apex: Point; right: Point; leftCtrl: Point; rightCtrl: Point };

function peaks(): Peak[] {
  const first = 92;
  const last = SIGER_WIDTH - 92;
  const spacing = (last - first) / (PEAKS - 1);
  const halfBase = spacing * 0.47;

  return Array.from({ length: PEAKS }, (_, i) => {
    const x = first + i * spacing;
    const distance = Math.abs(i - (PEAKS - 1) / 2) / ((PEAKS - 1) / 2); // 0 centre, 1 edge
    const height = 430 - distance * 230;
    const lean = (x - CENTER) * 0.14;
    const left: Point = [x - halfBase, topEdge(x - halfBase)];
    const right: Point = [x + halfBase, topEdge(x + halfBase)];
    const apex: Point = [x + lean, topEdge(x) - height];
    // Control points sit low and wide, so each side bulges like a leaf
    // before closing to its point.
    const leftCtrl: Point = [left[0] + (apex[0] - left[0]) * 0.08, left[1] - (left[1] - apex[1]) * 0.62];
    const rightCtrl: Point = [right[0] + (apex[0] - right[0]) * 0.08, right[1] - (right[1] - apex[1]) * 0.62];
    return { left, apex, right, leftCtrl, rightCtrl };
  });
}

function build(scaleX: number, scaleY: number): string {
  const digits = scaleX === 1 ? 1 : 5;
  const p = ([x, y]: Point) => `${(x * scaleX).toFixed(digits)} ${(y * scaleY).toFixed(digits)}`;

  const steps = 24;
  const bottom: string[] = [];
  for (let i = 1; i <= steps; i++) {
    const x = (SIGER_WIDTH * i) / steps;
    bottom.push(`L ${p([x, bottomEdge(x)])}`);
  }

  const top: string[] = [`L ${p([SIGER_WIDTH - 24, topEdge(SIGER_WIDTH - 24)])}`];
  for (const peak of [...peaks()].reverse()) {
    top.push(`L ${p(peak.right)}`);
    top.push(`Q ${p(peak.rightCtrl)} ${p(peak.apex)}`);
    top.push(`Q ${p(peak.leftCtrl)} ${p(peak.left)}`);
  }
  top.push(`L ${p([24, topEdge(24)])}`);

  return [`M ${p([0, bottomEdge(0)])}`, ...bottom, ...top, "Z"].join(" ");
}

/** Path in a 1000 × 600 box, for inline SVG. */
export const sigerPath = build(1, 1);

/** Same path normalised to 0–1, for clipPathUnits="objectBoundingBox" masks. */
export const sigerPathUnit = build(1 / SIGER_WIDTH, 1 / SIGER_HEIGHT);
