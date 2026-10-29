import { motion, useScroll, useTransform } from "motion/react";
import { useRef } from "react";
import { Link } from "react-router-dom";
import { Reveal } from "@/components/motion/Reveal";
import { SIGER_CLIP_ID } from "@/components/siger/SigerClip";

const BLOCKS = [
  {
    title: "Untuk ruang kendali",
    body: "Operator membaca kepadatan tiap simpang sebagai angka, tanpa memutar ulang rekaman. Admin menambah, mengubah, dan menonaktifkan kamera dari satu tempat.",
  },
  {
    title: "Rekaman tidak disimpan",
    body: "Frame hanya singgah beberapa detik di antrean untuk dibaca model. Yang masuk basis data hanya jumlah kendaraan per jenis dan waktunya.",
  },
];

export function About() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const drift = useTransform(scrollYProgress, [0, 1], ["8%", "-6%"]);

  return (
    <section id="tentang" aria-labelledby="tentang-title" className="bg-ground p-[10px] lg:p-5">
      <div
        ref={ref}
        className="relative flex flex-col overflow-hidden bg-deep px-5 pt-10 text-deep-ink lg:block lg:min-h-[110svh] lg:p-14"
      >
        <Reveal>
          <h2 id="tentang-title" className="text-[8.5vw] lg:text-head">
            Untuk Diskominfo
            <br />
            Bandar Lampung.
          </h2>
        </Reveal>

        <div className="mt-10 flex flex-col gap-12 lg:absolute lg:top-14 lg:left-[63%] lg:mt-0 lg:w-[300px] lg:gap-16">
          {BLOCKS.map((block, i) => (
            <Reveal key={block.title} order={i + 1}>
              <h3 className="text-lead leading-tight tracking-[-0.02em]">{block.title}</h3>
              <p className="mt-3">{block.body}</p>
            </Reveal>
          ))}
          <Reveal order={3}>
            <Link to="/masuk" className="siger-cut inline-block bg-accent px-7 pb-4 text-accent-ink hover:bg-ink">
              Masuk ke dasbor
            </Link>
          </Reveal>
        </div>

        {/* Jl. Pangeran Antasari under its Siger street lamps, cut to the Siger. */}
        <figure className="relative mx-auto mt-14 -mb-[6.2vw] w-[86vw] lg:absolute lg:bottom-[-3vw] lg:left-14 lg:m-0 lg:w-[46vw]">
          <motion.div className="aspect-[1000/600] overflow-hidden" style={{ clipPath: `url(#${SIGER_CLIP_ID})` }}>
            <motion.img
              src="/media/jalan-pangeran-antasari-bandar-lampung-lp-29.jpg"
              alt="Lalu lintas Jalan Pangeran Antasari, Bandar Lampung, dengan lampu jalan bermahkota siger"
              width={1478}
              height={2628}
              loading="lazy"
              className="h-[140%] w-full object-cover"
              style={{ y: drift, objectPosition: "50% 66%" }}
            />
          </motion.div>
        </figure>
      </div>
    </section>
  );
}
