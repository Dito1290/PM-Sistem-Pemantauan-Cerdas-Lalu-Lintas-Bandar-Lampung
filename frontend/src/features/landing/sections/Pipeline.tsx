import { useReducedMotion } from "motion/react";
import { Reveal } from "@/components/motion/Reveal";

/*
 * One card from the system, shown four times, further along each time:
 * a frame arrives, the model marks vehicles, they are counted, the count
 * is filed into the hourly statistics.
 */

const POSTER = "/media/ground-level-view-of-jalan-teknika-selatan-poster.jpg";
const CLIP = "/media/ground-level-view-of-jalan-teknika-selatan.webm";

// The source frame is 1920 × 1080; the card shows the 480 × 360 region at
// (760, 700) where three motorbikes pass. Boxes are % of that region.
const CROP = "absolute left-[-158.33%] top-[-194.44%] w-[400%] max-w-none";
const BOXES = [
  { left: "22.9%", top: "55.6%", width: "15.6%", height: "20.8%", score: "0,88" },
  { left: "44.8%", top: "56.9%", width: "13.5%", height: "19.4%", score: "0,91" },
  { left: "67.7%", top: "56.9%", width: "11.5%", height: "20.8%", score: "0,86" },
];

const HOURLY = [
  { label: "Mobil", value: 612 },
  { label: "Motor", value: 2041 },
  { label: "Bus", value: 37 },
  { label: "Truk", value: 124 },
];
const fmt = new Intl.NumberFormat("id-ID");

type Stage = 0 | 1 | 2 | 3;

const FIELDS: { tone: string; clause: string }[] = [
  { tone: "bg-surface text-ink", clause: "Pertama, kamera merekam simpang." },
  { tone: "bg-surface-2 text-ink", clause: "Lalu model menandai tiap kendaraan." },
  { tone: "bg-field text-field-ink", clause: "Lalu tiap jenis dihitung per frame." },
  { tone: "bg-deep text-deep-ink", clause: "Akhirnya angka masuk laporan per jam." },
];

export function Pipeline() {
  return (
    <section id="cara-kerja" aria-labelledby="cara-kerja-title">
      <div className="page-x grid gap-6 bg-ground pt-[clamp(80px,10vw,144px)] pb-10 lg:grid-cols-2 lg:items-end lg:gap-8 lg:pb-14">
        <Reveal>
          <h2 id="cara-kerja-title" className="text-head">
            Dari kamera ke angka
          </h2>
        </Reveal>
        <Reveal order={1}>
          <p className="max-w-[44ch]">
            Satu frame dari CAM-01 melewati empat tahap sebelum menjadi angka di dasbor. Tidak ada rekaman yang
            disimpan di sepanjang jalan.
          </p>
        </Reveal>
      </div>

      <ol className="m-0 grid list-none p-0 sm:grid-cols-2 lg:grid-cols-4">
        {FIELDS.map((field, i) => (
          <li key={field.clause} className={`flex min-h-[520px] flex-col gap-10 p-5 lg:min-h-[600px] lg:p-8 ${field.tone}`}>
            <Reveal order={i}>
              <PipelineCard stage={i as Stage} />
            </Reveal>
            <Reveal order={i + 1} className="mt-auto">
              <p className="max-w-[16ch] text-lead leading-[1.1] tracking-[-0.03em]">{field.clause}</p>
            </Reveal>
          </li>
        ))}
      </ol>
    </section>
  );
}

function PipelineCard({ stage }: { stage: Stage }) {
  return (
    <article
      className="w-full max-w-[320px] bg-ground text-ink transition-transform duration-150 ease-out hover:-translate-y-1.5"
    >
      <header data-ui className="flex items-baseline justify-between px-3 py-2 text-small">
        <span className="font-medium">CAM-01</span>
        <span style={{ fontVariantNumeric: "tabular-nums" }}>{stage === 3 ? "14.00–15.00" : "14.32.08"}</span>
      </header>

      {stage < 2 ? <Frame stage={stage} /> : null}
      {stage === 2 ? <FrameCounts /> : null}
      {stage === 3 ? <HourlyRow /> : null}

      <footer data-ui className="px-3 pt-1 pb-3 text-small font-medium">
        {["Menerima frame", "3 objek terdeteksi", "Total 3 kendaraan", "Tersimpan ke statistik per jam"][stage]}
      </footer>
    </article>
  );
}

function Frame({ stage }: { stage: Stage }) {
  const reduce = useReducedMotion();
  return (
    <figure className="m-0">
      <div className="relative aspect-[4/3] overflow-hidden bg-deep">
        {stage === 0 ? (
          <video
            className={CROP}
            autoPlay={!reduce}
            muted
            loop
            playsInline
            preload="metadata"
            poster={POSTER}
            width={854}
            height={480}
            aria-hidden="true"
          >
            <source src={CLIP} type="video/webm" />
          </video>
        ) : (
          <img className={CROP} src={POSTER} width={1920} height={1080} alt="" loading="lazy" />
        )}
        {stage === 1
          ? BOXES.map((box) => (
              <span
                key={box.left}
                data-ui
                className="absolute outline-2 outline-accent-ink"
                style={{ left: box.left, top: box.top, width: box.width, height: box.height }}
              >
                <span className="absolute -top-[1.35rem] left-[-2px] bg-accent px-1 text-small leading-[1.35rem] whitespace-nowrap text-accent-ink">
                  motor {box.score}
                </span>
              </span>
            ))
          : null}
      </div>
      {stage === 0 ? (
        <figcaption className="px-3 pt-2 text-small">Rekaman contoh dari jalan di Yogyakarta, bukan kamera sistem.</figcaption>
      ) : null}
    </figure>
  );
}

function FrameCounts() {
  const rows = [
    ["Mobil", 0],
    ["Motor", 3],
    ["Bus", 0],
    ["Truk", 0],
  ] as const;
  return (
    <dl data-ui className="m-0 grid grid-cols-2 gap-x-3 gap-y-4 px-3 py-4">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt className="text-small">{label}</dt>
          <dd className="m-0 text-lead font-medium" style={{ fontVariantNumeric: "tabular-nums" }}>
            {value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function HourlyRow() {
  const total = HOURLY.reduce((sum, row) => sum + row.value, 0);
  return (
    <div data-ui className="px-3 pb-3">
      <p className="m-0 text-head font-medium tracking-[-0.04em]" style={{ fontVariantNumeric: "tabular-nums" }}>
        {fmt.format(total)}
      </p>
      <p className="m-0 text-small">kendaraan dalam satu jam</p>
      <dl className="m-0 mt-3 grid grid-cols-4 gap-1 text-small">
        {HOURLY.map((row) => (
          <div key={row.label}>
            <dt>{row.label}</dt>
            <dd className="m-0 font-medium" style={{ fontVariantNumeric: "tabular-nums" }}>
              {fmt.format(row.value)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
