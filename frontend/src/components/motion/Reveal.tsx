import { motion } from "motion/react";
import type { ReactNode } from "react";

type RevealProps = {
  children: ReactNode;
  /** Position in the section's stagger; each step adds 75ms. */
  order?: number;
  className?: string;
};

/** Rises 24px and fades in once when it enters the viewport. */
export function Reveal({ children, order = 0, className }: RevealProps) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "0px 0px -10% 0px" }}
      transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: order * 0.075 }}
    >
      {children}
    </motion.div>
  );
}
