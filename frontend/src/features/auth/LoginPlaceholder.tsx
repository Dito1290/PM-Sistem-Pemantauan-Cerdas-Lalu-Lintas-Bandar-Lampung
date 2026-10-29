import { Link, useSearchParams } from "react-router-dom";

// Stage 2 replaces this with the real login form (POST /api/auth/login).
export function LoginPlaceholder() {
  const [params] = useSearchParams();
  const username = params.get("u");

  return (
    <main className="page-x flex min-h-svh flex-col justify-center gap-6">
      <h1 className="text-head">Halaman masuk menyusul.</h1>
      <p className="max-w-[40ch]">
        {username ? `Nama pengguna “${username}” sudah dicatat. ` : ""}
        Form masuk dan dasbor dibangun di tahap 2.
      </p>
      <Link to="/" className="underline underline-offset-4">
        Kembali ke beranda
      </Link>
    </main>
  );
}
