import { useId, useState } from "react";
import { AnimatedNumber } from "@/components/motion/AnimatedNumber";
import { Reveal } from "@/components/motion/Reveal";
import { Siger } from "@/components/siger/Siger";

// Values from backend/.env.example: MAX_ACTIVE_CAMERAS and FRAME_INTERVAL_SECONDS.
const CAMERAS = 3;
const FRAMES_PER_SECOND = 1 / 0.2;

const thousands = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });

export function FrameCalculator() {
  const [hours, setHours] = useState(12);
  const inputId = useId();
  const framesInThousands = (CAMERAS * FRAMES_PER_SECOND * 3600 * hours) / 1000;

  return (
    <section
      id="angka"
      aria-labelledby="angka-title"
      className="page-x flex flex-col bg-field pt-14 pb-14 text-field-ink lg:pt-20 lg:pb-16"
    >
      {/* The crown that divides the page in two, set once at the centre. */}
      <Reveal className="mx-auto w-[44vw] lg:w-[18vw]">
        <Siger className="block h-auto w-full" />
      </Reveal>

      <div className="mt-14 grid gap-10 lg:mt-20 lg:grid-cols-2 lg:gap-8">
        <Reveal>
          <h2 id="angka-title" className="text-lead tracking-[-0.03em] lg:text-head">
            Berapa jam kamera menyala?
          </h2>
        </Reveal>
        <Reveal order={1} className="w-full max-w-[400px] lg:pt-3">
          <div data-ui>
            <label htmlFor={inputId} className="flex items-baseline justify-between">
              <span>Jam menyala per hari</span>
              <span className="font-medium" style={{ fontVariantNumeric: "tabular-nums" }}>
                {hours} jam
              </span>
            </label>
            <input
              id={inputId}
              type="range"
              min={1}
              max={24}
              step={1}
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
              className="range mt-2"
            />
          </div>
        </Reveal>
      </div>

      <div className="mt-[clamp(64px,9vw,144px)] grid gap-6 lg:grid-cols-2 lg:items-end lg:gap-8">
        <p className="m-0 flex flex-col leading-[0.8] lg:flex-row lg:items-baseline lg:gap-[0.06em]">
          <AnimatedNumber
            value={framesInThousands}
            format={(n) => thousands.format(n)}
            className="text-[30vw] font-medium tracking-[-0.05em] lg:text-poster"
          />
          <span className="mt-3 text-lead lg:mt-0 lg:text-head lg:tracking-[-0.03em]">ribu frame</span>
        </p>
        <p className="max-w-[40ch]">
          {CAMERAS} kamera × 5 frame per detik (satu tiap 0,2 detik) × 3.600 detik × jam menyala. Semua angka dari
          konfigurasi sistem.
        </p>
      </div>
    </section>
  );
}
