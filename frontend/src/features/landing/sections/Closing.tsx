import { useId, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Reveal } from "@/components/motion/Reveal";

/** The closing sentence has a gap in it; the gap is the login field. */
export function Closing() {
  const [username, setUsername] = useState("");
  const navigate = useNavigate();
  const inputId = useId();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const name = username.trim();
    navigate(name ? `/masuk?u=${encodeURIComponent(name)}` : "/masuk");
  };

  return (
    <section id="masuk" aria-label="Masuk" className="page-x bg-ground py-[clamp(120px,14vw,220px)]">
      <Reveal>
        <form onSubmit={submit}>
          <p className="m-0 text-[9.5vw] leading-[1.05] font-medium tracking-[-0.05em] lg:text-display">
            Masuk sebagai{" "}
            <label htmlFor={inputId} className="sr-only">
              Nama pengguna
            </label>
            <input
              id={inputId}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="nama pengguna"
              autoComplete="username"
              className="my-[0.08em] block h-[1.1em] w-full bg-surface-2 px-[0.2em] align-baseline text-ink placeholder:text-muted focus:bg-surface focus:outline-none lg:inline-block lg:w-[7em]"
            />
            <br className="hidden lg:block" />
            lalu mulai{" "}
            <button
              type="submit"
              className="siger-cut inline-block bg-accent px-[0.2em] pb-[0.04em] text-accent-ink [--cut:0.14em] hover:bg-deep"
            >
              pantau.
            </button>
          </p>
        </form>
      </Reveal>
      <Reveal order={1}>
        <p className="mt-8 max-w-[52ch] text-muted">
          Kamu diarahkan ke halaman masuk dengan nama pengguna sudah terisi. Akun dibuat oleh admin Diskominfo.
        </p>
      </Reveal>
    </section>
  );
}
