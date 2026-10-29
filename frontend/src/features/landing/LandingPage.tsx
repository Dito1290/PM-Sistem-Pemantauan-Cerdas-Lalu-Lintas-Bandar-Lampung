import Lenis from "lenis";
import "lenis/dist/lenis.css";
import { MotionConfig } from "motion/react";
import { useEffect } from "react";
import { SigerClipDefs } from "@/components/siger/SigerClip";
import { Hero } from "./sections/Hero";
import { CameraMap } from "./sections/CameraMap";
import { Pipeline } from "./sections/Pipeline";
import { Capabilities } from "./sections/Capabilities";
import { FrameCalculator } from "./sections/FrameCalculator";
import { About } from "./sections/About";
import { Closing } from "./sections/Closing";
import { SiteFooter } from "./sections/SiteFooter";

export function LandingPage() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const lenis = new Lenis({ autoRaf: true, anchors: true, lerp: 0.12 });
    return () => lenis.destroy();
  }, []);

  return (
    <MotionConfig reducedMotion="user">
      <SigerClipDefs />
      <main>
        <Hero />
        <CameraMap />
        <Pipeline />
        <Capabilities />
        <FrameCalculator />
        <About />
        <Closing />
      </main>
      <SiteFooter />
    </MotionConfig>
  );
}
