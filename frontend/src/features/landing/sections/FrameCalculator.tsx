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
    <>
      {/* The band of crowns that divides the page in two. */}
      <div aria-hidden="true" className="flex items-end bg-ground text-field">
        {Array.from({ length: 6 }, (_, i) => (
          <Siger key={i} className={`-mb-px w-1/3 shrink-0 lg:w-1/6 ${i > 2 ? "hidden lg:block" : ""}`} />
        ))}
      </div>

      <section
        id="angka"
        aria-labelledby="angka-title"
        className="page-x flex min-h-[84svh] flex-col justify-between gap-16 bg-field py-14 text-field-ink lg:min-h-[88svh] lg:py-16"
      >
        <div>
          <Reveal>
            <h2 id="angka-title" className="text-lead tracking-[-0.03em] lg:text-head">
              Berapa jam kamera menyala?
            </h2>
          </Reveal>
          <Reveal order={1} className="mt-7 w-full max-w-[400px]">
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

        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <p className="m-0 flex flex-col leading-[0.8] lg:flex-row lg:items-baseline lg:gap-[0.06em]">
            <AnimatedNumber
              value={framesInThousands}
              format={(n) => thousands.format(n)}
              className="text-[30vw] font-medium tracking-[-0.05em] lg:text-poster"
            />
            <span className="mt-3 text-[1.25rem] lg:mt-0 lg:text-head lg:tracking-[-0.03em]">
              ribu frame
            </span>
          </p>
          <p className="max-w-[30ch] text-body">
            {CAMERAS} kamera × 5 frame per detik (satu tiap 0,2 detik) × 3.600 detik × jam menyala. Semua angka dari
            konfigurasi sistem.
          </p>
        </div>
      </section>
    </>
  );
}
