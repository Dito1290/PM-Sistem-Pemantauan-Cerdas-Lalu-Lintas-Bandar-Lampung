import { motion } from "motion/react";
import type { ReactNode } from "react";

/*
 * A board of close-ups: each tile enlarges one real control or readout from
 * the dashboard (built in em, scaled through the root font size). Blocks run
 * off the tile edges; their words stay whole.
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
      className={`group relative overflow-hidden ${TONES[tone]} ${layout}`}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "0px 0px -10% 0px" }}
      transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: (order % 4) * 0.075 }}
    >
      <div data-ui className="absolute inset-0 transition-transform duration-500 ease-out group-hover:scale-[1.04]">
        {children}
      </div>
      <div className="absolute bottom-5 left-5 right-5">
        <h3 className="text-body leading-tight font-medium tracking-[-0.01em]">{name}</h3>
        <p className="mt-1 text-small leading-snug">{line}</p>
      </div>
    </motion.li>
  );
}

const tabular = { fontVariantNumeric: "tabular-nums" } as const;

export function Capabilities() {
  return (
    <section id="kemampuan" aria-labelledby="kemampuan-title" className="bg-ground p-[6px] lg:p-[10px]">
      <ul className="m-0 grid list-none auto-rows-[28vw] grid-cols-2 gap-[6px] p-0 lg:auto-rows-[104px] lg:grid-cols-12 lg:gap-2">
        <li className="col-span-2 row-span-2 bg-surface-2 p-5 lg:col-span-6 lg:col-start-1 lg:row-start-1">
          <h2 id="kemampuan-title" className="text-[9vw] lg:text-head">
            Yang dilihat operator
          </h2>
        </li>

        <Tile
          tone="field"
          layout="col-span-2 row-span-3 lg:col-span-6 lg:row-span-4 lg:col-start-7 lg:row-start-1"
          name="Empat jenis kendaraan"
          line="Mobil, motor, bus, dan truk dihitung terpisah."
          order={0}
        >
          <div data-ui className="absolute top-[14%] left-[6%] flex flex-wrap gap-[0.3em] pr-[6%] text-[2.2rem] lg:text-head">
            {["Mobil", "Motor", "Bus", "Truk"].map((label) => (
              <span
                key={label}
                className={`px-[0.4em] py-[0.12em] whitespace-nowrap ${label === "Motor" ? "bg-deep text-deep-ink" : "bg-ground text-ink"}`}
              >
                {label}
              </span>
            ))}
          </div>
        </Tile>

        <Tile
          tone="deep"
          layout="row-span-2 lg:col-span-3 lg:row-span-4 lg:col-start-1 lg:row-start-3"
          name="Status tiap kamera"
          line="Online, offline, atau menyambung ulang."
          order={1}
        >
          <div
            data-ui
            className="absolute top-[12%] right-[-2em] flex items-center gap-[0.35em] bg-ground py-[0.15em] pr-[2.4em] pl-[0.45em] text-[1.6rem] text-ink lg:text-head"
          >
            <span className="inline-block size-[0.42em] rounded-full bg-[#2f7d32]" aria-hidden="true" />
            Online
          </div>
        </Tile>

        <Tile
          tone="surface"
          layout="row-span-2 lg:col-span-3 lg:row-span-2 lg:col-start-4 lg:row-start-3"
          name="Dua peran"
          line="Admin mengelola kamera, operator memantau."
          order={2}
        >
          <div data-ui className="absolute top-[10%] right-[8%] flex pl-[0.3em] text-[1.1rem] lg:text-lead">
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
          <div data-ui className="absolute top-[-0.35em] right-[-0.5em] text-[2.6rem] lg:text-head">
            <span className="relative block h-[1.1em] w-[2em] rounded-full bg-field-ink">
              <span className="absolute top-[0.12em] right-[0.12em] size-[0.86em] rounded-full bg-deep" />
            </span>
          </div>
        </Tile>

        <Tile
          tone="surface"
          layout="row-span-2 lg:col-span-6 lg:row-span-2 lg:col-start-7 lg:row-start-5"
          name="Statistik per jam dan harian"
          line="Rentang sampai 31 hari, laporan harian sampai setahun."
          order={0}
        >
          <div data-ui className="absolute top-[18%] left-[38%] w-[22em] text-[1rem] lg:text-lead">
            <span className="relative block h-[0.3em] w-full bg-surface-2">
              <span className="absolute inset-y-0 left-0 w-[46%] bg-ink" />
              <span className="absolute top-1/2 left-[46%] size-[1.1em] -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink" />
            </span>
            <span className="mt-[0.5em] block w-[46%] text-right font-medium">24 jam</span>
          </div>
        </Tile>

        <Tile
          tone="surface-2"
          layout="col-span-2 row-span-3 lg:col-span-6 lg:row-span-4 lg:col-start-1 lg:row-start-7"
          name="Angka tanpa muat ulang"
          line="Data baru didorong ke layar lewat Server-Sent Events."
          order={1}
        >
          <div data-ui className="absolute bottom-[34%] left-5 leading-[0.9] text-[22vw] lg:top-[8%] lg:bottom-auto lg:text-poster">
            <span className="font-medium tracking-[-0.05em]" style={tabular}>
              1.284
            </span>
          </div>
        </Tile>

        <Tile
          tone="field"
          layout="row-span-2 lg:col-span-3 lg:row-span-4 lg:col-start-7 lg:row-start-7"
          name="Ambang keyakinan 0,70"
          line="Deteksi yang ragu tidak ikut dihitung."
          order={2}
        >
          <div
            data-ui
            className="absolute top-[30%] left-[-1em] bg-ground py-[0.05em] pr-[0.3em] pl-[1.2em] text-[1.6rem] font-medium text-ink lg:text-head"
            style={tabular}
          >
            ≥ 0,70
          </div>
        </Tile>

        <Tile
          tone="deep"
          layout="row-span-2 lg:col-span-3 lg:row-span-4 lg:col-start-10 lg:row-start-7"
          name="Sesi 60 menit"
          line="Token masuk kedaluwarsa sendiri."
          order={3}
        >
          <div data-ui className="absolute top-[30%] left-5 text-[1.6rem] font-medium lg:text-head" style={tabular}>
            59:41
          </div>
        </Tile>
      </ul>
    </section>
  );
}
