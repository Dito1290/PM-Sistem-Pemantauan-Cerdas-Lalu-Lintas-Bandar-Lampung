import { motion, useScroll, useTransform } from "motion/react";
import { useRef } from "react";
import { SiteNav } from "@/components/layout/SiteNav";
import { SIGER_HEIGHT, SIGER_WIDTH, sigerPath } from "@/components/siger/sigerPath";

const EASE = [0.22, 1, 0.36, 1] as const;

export function Hero() {
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const drift = useTransform(scrollYProgress, [0, 1], ["0%", "16%"]);
  const tilt = useTransform(scrollYProgress, [0, 1], [0, -4]);

  return (
    <section ref={ref} className="relative min-h-[100svh] overflow-hidden bg-ground">
      <SiteNav />

      {/* The Siger at city scale, filled with the city it crowns. */}
      <motion.div
        className="absolute left-[-15vw] top-[56svh] w-[130vw] lg:left-[calc(84%-66vh)] lg:top-[calc(60%-39.6vh)] lg:w-[132vh]"
        style={{ y: drift, rotate: tilt }}
      >
        <motion.svg
          viewBox={`0 0 ${SIGER_WIDTH} ${SIGER_HEIGHT}`}
          role="img"
          className="h-auto w-full text-accent"
          initial={{ y: "14%", opacity: 0 }}
          animate={{ y: "0%", opacity: 1 }}
          transition={{ duration: 1.3, ease: EASE, delay: 0.15 }}
        >
          <title>Siger berisi panorama Bandar Lampung dan Teluk Lampung</title>
          <defs>
            <clipPath id="hero-siger">
              <path d={sigerPath} />
            </clipPath>
          </defs>
          <g clipPath="url(#hero-siger)">
            <rect width={SIGER_WIDTH} height={SIGER_HEIGHT} fill="currentColor" />
            <motion.image
              href="/media/skyline-of-bandar-lampung-from-bukit-randu.jpg"
              x={-60}
              y={-20}
              width={SIGER_WIDTH + 120}
              height={SIGER_HEIGHT + 40}
              preserveAspectRatio="xMidYMid slice"
              style={{ mixBlendMode: "multiply", filter: "grayscale(1) contrast(1.15)" }}
              initial={{ scale: 1.12 }}
              animate={{ scale: 1 }}
              transition={{ duration: 2.4, ease: EASE }}
            />
          </g>
        </motion.svg>
      </motion.div>

      <div className="page-x relative z-10 flex min-h-[100svh] flex-col pt-[15svh] lg:justify-center lg:pt-0 lg:pl-[8%]">
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
          className="mt-6 max-w-[34ch] text-body lg:mt-8"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: EASE, delay: 0.35 }}
        >
          Tiga CCTV di jalan Bandar Lampung dibaca model deep learning. Mobil, motor, bus, dan truk dihitung
          lima kali per detik untuk Diskominfo.
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
