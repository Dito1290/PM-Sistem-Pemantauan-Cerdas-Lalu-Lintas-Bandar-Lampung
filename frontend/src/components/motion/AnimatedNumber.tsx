import { animate, useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";

const formatter = new Intl.NumberFormat("id-ID");

type AnimatedNumberProps = {
  value: number;
  format?: (n: number) => string;
  className?: string;
};

/** Counts from the previous value to the new one instead of jumping. */
export function AnimatedNumber({ value, format = (n) => formatter.format(n), className }: AnimatedNumberProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const previous = useRef(value);
  const reduce = useReducedMotion();

  useEffect(() => {
    const controls = animate(previous.current, value, {
      duration: reduce ? 0 : 0.6,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => {
        if (ref.current) ref.current.textContent = format(Math.round(v));
      },
    });
    previous.current = value;
    return () => controls.stop();
  }, [value, format, reduce]);

  return (
    <span ref={ref} className={className} style={{ fontVariantNumeric: "tabular-nums" }}>
      {format(value)}
    </span>
  );
}
