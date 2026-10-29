import { motion } from "motion/react";
import type { ReactNode } from "react";
import { CAMERAS } from "../data/cameras";

/*
 * A board of close-ups: each tile enlarges one real control or readout from
 * the dashboard. Every tile follows the same frame: the element sits at the
 * top-left padding, the caption at the bottom-left, nothing is cropped.
 */

type Tone = "surface" | "surface-2" | "field" | "deep";

const TONES: Record<Tone, string> = {
  surface: "bg-surface text-ink",
  "surface-2": "bg-surface-2 text-ink",
  field: "bg-field text-field-ink",
  deep: "bg-deep text-deep-ink",
};

type TileProps = {
  tone: Tone;
  layout: string;
  name: string;
  line: string;
  order: number;
  children: ReactNode;
};

function Tile({ tone, layout, name, line, order, children }: TileProps) {
  return (
    <motion.li
      className={`group flex flex-col justify-between gap-6 p-5 lg:p-6 ${TONES[tone]} ${layout}`}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "0px 0px -10% 0px" }}
      transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: (order % 4) * 0.075 }}
    >
      <div data-ui className="origin-top-left transition-transform duration-500 ease-out group-hover:scale-[1.03]">
        {children}
      </div>
      <div>
        <h3 className="text-body leading-tight font-medium tracking-[-0.01em]">{name}</h3>
        <p className="mt-1 text-small leading-snug">{line}</p>
      </div>
    </motion.li>
  );
}

const tabular = { fontVariantNumeric: "tabular-nums" } as const;

const STATUS: Record<number, { word: string; on: boolean }> = {
  1: { word: "Online", on: true },
  2: { word: "Online", on: true },
  3: { word: "Menyambung", on: false },
};

export function Capabilities() {
  return (
    <section id="kemampuan" aria-labelledby="kemampuan-title" className="bg-ground px-[6px] pb-[6px] lg:px-2 lg:pb-2">
      <ul className="m-0 grid list-none auto-rows-[minmax(28vw,auto)] grid-cols-2 gap-[6px] p-0 lg:auto-rows-[104px] lg:grid-cols-12 lg:gap-2">
        <li className="col-span-2 row-span-2 flex flex-col justify-between gap-6 bg-surface-2 p-5 lg:col-span-6 lg:col-start-1 lg:row-start-1 lg:p-6">
          <h2 id="kemampuan-title" className="text-[9vw] lg:text-head">
            Yang dilihat operator
          </h2>
          <p className="max-w-[44ch]">Delapan bagian dasbor, diperbesar dari layar aslinya.</p>
        </li>

        <Tile
          tone="field"
          layout="col-span-2 row-span-3 lg:col-span-6 lg:row-span-4 lg:col-start-7 lg:row-start-1"
          name="Empat jenis kendaraan"
          line="Mobil, motor, bus, dan truk dihitung terpisah."
          order={0}
        >
          <div className="grid w-max grid-cols-2 gap-2 text-[2rem] lg:text-head">
            {["Mobil", "Motor", "Bus", "Truk"].map((label) => (
              <span
                key={label}
                className={`px-[0.35em] py-[0.08em] ${label === "Motor" ? "bg-deep text-deep-ink" : "bg-ground text-ink"}`}
              >
                {label}
              </span>
            ))}
          </div>
        </Tile>

        <Tile
          tone="deep"
          layout="col-span-2 row-span-2 lg:col-span-3 lg:row-span-4 lg:col-start-1 lg:row-start-3"
          name="Status tiap kamera"
          line="Online, offline, atau menyambung ulang."
          order={1}
        >
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {CAMERAS.map((camera) => (
              <li key={camera.id} className="flex items-center justify-between gap-3 bg-ground px-3 py-2 text-small text-ink">
                <span>{camera.name}</span>
                <span className="flex items-center gap-2 font-medium whitespace-nowrap">
                  <span
                    aria-hidden="true"
                    className={`inline-block size-2.5 rounded-full ${STATUS[camera.id].on ? "bg-[#2f7d32]" : "bg-[#b26a00]"}`}
                  />
                  {STATUS[camera.id].word}
                </span>
              </li>
            ))}
          </ul>
        </Tile>

        <Tile
          tone="surface"
          layout="row-span-2 lg:col-span-3 lg:row-span-2 lg:col-start-4 lg:row-start-3"
          name="Dua peran"
          line="Admin mengelola kamera, operator memantau."
          order={2}
        >
          <div className="flex pl-[0.3em] text-lead">
            {["AD", "OP", "OP"].map((initials, i) => (
              <span
                key={i}
                className={`-ml-[0.3em] flex size-[2.2em] items-center justify-center rounded-full font-medium ${i === 0 ? "bg-ink text-accent-ink" : "bg-surface-2 text-ink"}`}
                style={{ boxShadow: "0 0 0 0.14em var(--color-surface)" }}
              >
                {initials}
              </span>
            ))}
          </div>
        </Tile>

        <Tile
          tone="field"
          layout="row-span-2 lg:col-span-3 lg:row-span-2 lg:col-start-4 lg:row-start-5"
          name="Tiga kamera aktif"
          line="Batas kamera aktif dijaga sistem."
          order={3}
        >
          <span className="relative block h-[1.1em] w-[2em] rounded-full bg-field-ink text-[2.25rem] lg:text-head">
            <span className="absolute top-[0.12em] right-[0.12em] size-[0.86em] rounded-full bg-deep" />
          </span>
        </Tile>

        <Tile
          tone="surface"
          layout="col-span-2 row-span-2 lg:col-span-6 lg:row-span-2 lg:col-start-7 lg:row-start-5"
          name="Statistik per jam dan harian"
          line="Rentang sampai 31 hari, laporan harian sampai setahun."
          order={0}
        >
          <div className="text-lead">
            <span className="relative block h-[0.3em] w-full bg-surface-2">
              <span className="absolute inset-y-0 left-0 w-[46%] bg-ink" />
              <span className="absolute top-1/2 left-[46%] size-[1.1em] -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink" />
            </span>
            <span className="mt-[0.6em] flex justify-between text-body">
              <span>1 jam</span>
              <span className="font-medium">24 jam</span>
              <span>31 hari</span>
            </span>
          </div>
        </Tile>

        <Tile
          tone="surface-2"
          layout="col-span-2 row-span-3 lg:col-span-6 lg:row-span-4 lg:col-start-1 lg:row-start-7"
          name="Angka tanpa muat ulang"
          line="Data baru didorong ke layar lewat Server-Sent Events."
          order={1}
        >
          <span className="block text-[22vw] leading-[0.85] font-medium tracking-[-0.05em] lg:text-poster" style={tabular}>
            1.284
          </span>
        </Tile>

        <Tile
          tone="field"
          layout="row-span-2 lg:col-span-3 lg:row-span-4 lg:col-start-7 lg:row-start-7"
          name="Ambang keyakinan 0,70"
          line="Deteksi yang ragu tidak ikut dihitung."
          order={2}
        >
          <span className="inline-block bg-ground px-[0.25em] text-[2rem] font-medium text-ink lg:text-head" style={tabular}>
            ≥ 0,70
          </span>
        </Tile>

        <Tile
          tone="deep"
          layout="row-span-2 lg:col-span-3 lg:row-span-4 lg:col-start-10 lg:row-start-7"
          name="Sesi 60 menit"
          line="Token masuk kedaluwarsa sendiri."
          order={3}
        >
          <span className="block text-[2rem] font-medium lg:text-head" style={tabular}>
            59:41
          </span>
        </Tile>
      </ul>
    </section>
  );
}
