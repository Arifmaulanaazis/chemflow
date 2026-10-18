import { lazy, Suspense, useEffect, useState } from "react";
import { Button, Notice } from "../components/atoms";
import { Download, BookOpen } from "../components/atoms/Icons";
import { api } from "../lib/api";
const PdfReader = lazy(() => import("./PdfReader"));
interface Citation {
  id: string;
  title: string;
  authors: string;
  year: string;
  url: string;
  usage: string;
  version?: string;
}
export default function LibraryPage() {
  const [citations, setCitations] = useState<Citation[]>([]),
    [error, setError] = useState(""),
    [copied, setCopied] = useState(false);
  useEffect(() => {
    api<Citation[]>("/citations")
      .then(setCitations)
      .catch((e) => setError(e.message));
  }, []);
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Materi & sitasi</h1>
          <p>
            Baca workshop ChemFlow dan temukan referensi metode yang digunakan.
          </p>
        </div>
        <BookOpen size={34} aria-hidden="true" />
      </div>
      <section className="panel library-panel">
        <div className="section-heading">
          <div>
            <h2>Panduan & workshop</h2>
            <p>Materi lengkap ChemFlow, termasuk CLI dan WebUI.</p>
          </div>
          <div className="library-downloads">
            <a
              className="button secondary"
              href="/api/library/guide/file?format=pdf"
              download="chemflow.pdf"
            >
              <Download size={16} aria-hidden="true" />
              PDF
            </a>
            <a
              className="button secondary"
              href="/api/library/guide/file?format=pptx"
              download
            >
              <Download size={16} aria-hidden="true" />
              PowerPoint
            </a>
          </div>
        </div>
        <Suspense fallback={<p role="status">Menyiapkan pembaca PDF…</p>}>
          <PdfReader />
        </Suspense>
      </section>
      <section className="panel citations-panel">
        <div className="section-heading">
          <div>
            <h2>Sitasi perangkat lunak & metode</h2>
            <p>
              Sitasi metode yang benar-benar digunakan pada eksperimen Anda.
            </p>
          </div>
          <a className="button secondary" href="/api/citations/bibtex" download>
            BibTeX
          </a>
        </div>
        {error && <Notice>{error}</Notice>}
        <ol className="citation-list">
          {citations.map((c) => (
            <li key={c.id}>
              <strong>
                {c.title}
                {c.version ? ` v${c.version}` : ""}
              </strong>
              <p>
                {c.authors} ({c.year})
              </p>
              <a href={c.url} target="_blank" rel="noreferrer">
                {c.url.replace("https://", "")}
              </a>
              <small>{c.usage}</small>
            </li>
          ))}
        </ol>
        <Button
          variant="secondary"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(
                citations
                  .map(
                    (c) =>
                      `${c.authors} (${c.year}). ${c.title}${c.version ? ` v${c.version}` : ""}. ${c.url}`,
                  )
                  .join("\n\n"),
              );
              setCopied(true);
            } catch {
              setError(
                "Penyalinan memerlukan HTTPS/localhost. Unduh BibTeX atau pilih teks referensi.",
              );
            }
          }}
        >
          {copied ? "Referensi disalin" : "Salin referensi"}
        </Button>
        <p className="citation-note">
          Sebutkan versi ChemFlow dan dependensi yang digunakan, parameter
          docking, serta ID dan publikasi struktur PDB. Referensi ini bukan
          bukti validasi biologis hasil docking.
        </p>
      </section>
    </>
  );
}
