import { motion, useScroll, useTransform } from "motion/react";
import { useRef } from "react";
import { SiteNav } from "@/components/layout/SiteNav";
import { SIGER_CLIP_ID } from "@/components/siger/SigerClip";

const EASE = [0.22, 1, 0.36, 1] as const;

export function Hero() {
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const drift = useTransform(scrollYProgress, [0, 1], ["0%", "12%"]);

  return (
    <section ref={ref} className="relative min-h-[100svh] overflow-hidden bg-ground">
      <SiteNav />

      {/*
        The Siger at city scale, filled with the city it crowns. It is anchored
        to the bottom-right corner: the right and bottom edges crop it, the
        left tip stays clear of the headline.
      */}
      <motion.div
        role="img"
        aria-label="Siger berisi panorama Bandar Lampung dan Teluk Lampung"
        className="absolute right-[-30vw] bottom-[-6svh] w-[160vw] lg:right-[-12vw] lg:bottom-[-7svh] lg:w-[125vh]"
        style={{ y: drift }}
      >
        <motion.div
          className="relative aspect-[1000/600] w-full overflow-hidden bg-accent"
          style={{ clipPath: `url(#${SIGER_CLIP_ID})` }}
          initial={{ y: "12%", opacity: 0 }}
          animate={{ y: "0%", opacity: 1 }}
          transition={{ duration: 1.3, ease: EASE, delay: 0.15 }}
        >
          <motion.img
            src="/media/skyline-of-bandar-lampung-from-bukit-randu.jpg"
            alt=""
            width={1920}
            height={1080}
            fetchPriority="high"
            className="absolute inset-0 h-full w-full object-cover"
            style={{ mixBlendMode: "multiply", filter: "grayscale(1) contrast(1.15)" }}
            initial={{ scale: 1.12 }}
            animate={{ scale: 1 }}
            transition={{ duration: 2.4, ease: EASE }}
          />
        </motion.div>
      </motion.div>

      <div className="page-x relative z-10 flex min-h-[100svh] flex-col pt-[16svh] lg:justify-center lg:pt-0">
        <h1 className="text-[11.5vw] lg:text-display">
          {["Jalan kota,", "terhitung."].map((line, i) => (
            <span key={line} className="block overflow-hidden pb-[0.08em]">
              <motion.span
                className="block"
                initial={{ y: "105%" }}
                animate={{ y: "0%" }}
                transition={{ duration: 0.9, ease: EASE, delay: 0.1 + i * 0.09 }}
              >
                {line}
              </motion.span>
            </span>
          ))}
        </h1>
        <motion.p
          className="mt-6 max-w-[36ch] lg:mt-8"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: EASE, delay: 0.35 }}
        >
          CCTV di depan SD 2 Rajabasa, Underpass Unila, dan Tugu Adipura dibaca model deep learning. Mobil,
          motor, bus, dan truk dihitung lima kali per detik untuk Diskominfo.
        </motion.p>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: EASE, delay: 0.45 }}
        >
          <a href="#peta" className="siger-cut mt-8 inline-block bg-accent px-7 pb-4 text-accent-ink">
            Lihat peta kamera
          </a>
        </motion.div>
      </div>
    </section>
  );
}
