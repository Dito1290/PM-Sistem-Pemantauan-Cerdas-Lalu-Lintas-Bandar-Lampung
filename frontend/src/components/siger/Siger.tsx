import type { SVGProps } from "react";
import { SIGER_HEIGHT, SIGER_WIDTH, sigerPath } from "./sigerPath";

type SigerProps = SVGProps<SVGSVGElement> & { title?: string };

/** The Siger as a flat filled shape. Colour comes from `currentColor`. */
export function Siger({ title, ...props }: SigerProps) {
  return (
    <svg
      viewBox={`0 0 ${SIGER_WIDTH} ${SIGER_HEIGHT}`}
      fill="currentColor"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      {...props}
    >
      {title ? <title>{title}</title> : null}
      <path d={sigerPath} />
    </svg>
  );
}
