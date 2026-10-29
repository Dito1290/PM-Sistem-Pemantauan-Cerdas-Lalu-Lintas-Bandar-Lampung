import { motion, useScroll, useTransform } from "motion/react";
import { useRef } from "react";
import { Link } from "react-router-dom";
import { Reveal } from "@/components/motion/Reveal";
import { SIGER_CLIP_ID } from "@/components/siger/SigerClip";

const BLOCKS = [
  {
    title: "Untuk ruang kendali",
    body: "Operator membaca kepadatan tiap titik sebagai angka, tanpa memutar ulang rekaman. Admin menambah, mengubah, dan menonaktifkan kamera dari satu tempat.",
  },
  {
    title: "Rekaman tidak disimpan",
    body: "Frame hanya singgah beberapa detik di antrean untuk dibaca model. Yang masuk basis data hanya jumlah kendaraan per jenis dan waktunya.",
  },
];

export function About() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const drift = useTransform(scrollYProgress, [0, 1], ["-6%", "6%"]);

  return (
    <section id="tentang" aria-labelledby="tentang-title" className="bg-ground p-[10px] lg:p-5">
      <div
        ref={ref}
        className="grid gap-12 bg-deep px-5 py-12 text-deep-ink lg:grid-cols-2 lg:gap-8 lg:p-14"
      >
        <div className="flex flex-col justify-between gap-12">
          <Reveal>
            <h2 id="tentang-title" className="text-[8.5vw] lg:text-head">
              Untuk Diskominfo
              <br />
              Bandar Lampung.
            </h2>
          </Reveal>

          {/* Jl. Pangeran Antasari under its Siger street lamps, cut to the Siger. */}
          <Reveal order={1}>
            <figure className="m-0">
              <div className="aspect-[1000/600] w-full overflow-hidden" style={{ clipPath: `url(#${SIGER_CLIP_ID})` }}>
                <motion.img
                  src="/media/jalan-pangeran-antasari-bandar-lampung-lp-29.jpg"
                  alt="Lalu lintas Jalan Pangeran Antasari, Bandar Lampung, dengan lampu jalan bermahkota siger"
                  width={1478}
                  height={2628}
                  loading="lazy"
                  className="h-[125%] w-full object-cover"
                  style={{ y: drift, objectPosition: "50% 66%" }}
                />
              </div>
              <figcaption className="mt-3 text-small">Jl. Pangeran Antasari, Bandar Lampung.</figcaption>
            </figure>
          </Reveal>
        </div>

        <div className="flex flex-col gap-12 lg:max-w-[440px] lg:justify-self-end">
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
      </div>
    </section>
  );
}
