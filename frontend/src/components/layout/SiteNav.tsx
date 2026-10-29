import { Link } from "react-router-dom";

const LINKS = [
  { href: "#peta", label: "Peta kamera" },
  { href: "#cara-kerja", label: "Cara kerja" },
  { href: "#kemampuan", label: "Kemampuan" },
];

export function SiteNav() {
  return (
    <header className="page-x absolute inset-x-0 top-0 z-20 flex items-center justify-between py-5">
      <Link to="/" className="text-lead font-medium tracking-[-0.04em]">
        CitySight
      </Link>
      <nav aria-label="Utama" className="flex items-center gap-8">
        <ul className="hidden items-center gap-8 lg:flex">
          {LINKS.map((link) => (
            <li key={link.href}>
              <a href={link.href} className="underline-offset-4 hover:underline">
                {link.label}
              </a>
            </li>
          ))}
        </ul>
        <Link to="/masuk" className="siger-cut bg-accent px-5 pb-2 text-accent-ink">
          Masuk
        </Link>
      </nav>
    </header>
  );
}
