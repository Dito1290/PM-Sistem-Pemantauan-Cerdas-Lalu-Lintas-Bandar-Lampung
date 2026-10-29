import { sigerPathUnit } from "./sigerPath";

export const SIGER_CLIP_ID = "siger-clip";

/**
 * Registers the Siger as a reusable clip path. Render once per page, then
 * mask any element with `style={{ clipPath: `url(#${SIGER_CLIP_ID})` }}`.
 */
export function SigerClipDefs() {
  return (
    <svg width="0" height="0" aria-hidden="true" style={{ position: "absolute" }}>
      <defs>
        <clipPath id={SIGER_CLIP_ID} clipPathUnits="objectBoundingBox">
          <path d={sigerPathUnit} />
        </clipPath>
      </defs>
    </svg>
  );
}
