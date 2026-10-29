import { Link } from "react-router-dom";
import { Siger } from "@/components/siger/Siger";
import { CREDITS } from "../data/credits";

const COLUMNS = [
  {
    title: "Halaman",
    links: [
      { label: "Peta kamera", href: "#peta" },
      { label: "Cara kerja", href: "#cara-kerja" },
      { label: "Kemampuan", href: "#kemampuan" },
      { label: "Tentang", href: "#tentang" },
    ],
  },
  {
    title: "Akses",
    links: [
      { label: "Masuk", to: "/masuk" },
      { label: "Hitung frame", href: "#angka" },
    ],
  },
  {
    title: "Sumber",
    links: [
      { label: "Seribu Wajah", href: "https://seribuwajah.bandarlampungkota.go.id/map", external: true },
      { label: "OpenStreetMap", href: "https://www.openstreetmap.org/copyright", external: true },
    ],
  },
] as const;

export function SiteFooter() {
  return (
    <footer className="page-x bg-field pt-14 pb-6 text-field-ink lg:pt-20">
      {/* The mark, built large: the Siger beside the name. */}
      <div className="flex flex-col items-start gap-2 lg:flex-row lg:items-end lg:gap-[0.12em] lg:text-poster">
        <Siger className="h-auto w-[40vw] lg:h-[0.72em] lg:w-auto" />
        <p className="m-0 text-[18vw] leading-[0.8] font-medium tracking-[-0.06em] lg:text-[1em]">CitySight</p>
      </div>

      <div className="mt-14 grid grid-cols-2 gap-x-6 gap-y-10 text-body lg:grid-cols-12">
        {COLUMNS.map((column) => (
          <nav key={column.title} aria-label={column.title} className="lg:col-span-2">
            <h2 className="text-body font-medium tracking-normal">{column.title}</h2>
            <ul className="mt-3 flex list-none flex-col gap-2 p-0">
              {column.links.map((link) => (
                <li key={link.label}>
                  {"to" in link ? (
                    <Link to={link.to} className="underline-offset-4 hover:underline">
                      {link.label}
                    </Link>
                  ) : (
                    <a
                      href={link.href}
                      className="underline-offset-4 hover:underline"
                      {...("external" in link ? { target: "_blank", rel: "noreferrer" } : {})}
                    >
                      {link.label}
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </nav>
        ))}

        <div className="col-span-2 lg:col-span-4 lg:col-start-9">
          <p className="m-0">Dinas Komunikasi dan Informatika Kota Bandar Lampung</p>
          <p className="mt-3">Proyek Mandiri, Semester 5. Sistem Pemantauan Cerdas Lalu Lintas berbasis deep learning.</p>
        </div>
      </div>

      <div className="mt-14 max-w-[110ch] text-small leading-relaxed">
        <h2 className="text-small font-medium tracking-normal">Kredit foto</h2>
        <p className="mt-2">
          {CREDITS.map((credit, i) => (
            <span key={credit.page}>
              <a href={credit.page} target="_blank" rel="noreferrer" className="underline underline-offset-2">
                “{credit.title}”
              </a>{" "}
              oleh {credit.creator}, {credit.license}, via Wikimedia Commons ({credit.usedFor})
              {i < CREDITS.length - 1 ? ". " : "."}
            </span>
          ))}{" "}
          Peta © OpenStreetMap contributors.
        </p>
      </div>

      <div className="mt-10 flex items-center justify-between gap-4 text-small">
        <p className="m-0">© 2026 CitySight Bandar Lampung</p>
        <a href="#top" onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: "smooth" }); }} className="siger-cut bg-ground px-4 pb-2 text-ink">
          Ke atas
        </a>
      </div>
    </footer>
  );
}
