import Disclosure from "../components/atoms/Disclosure";
import { useState, type ReactNode } from "react";
import { Search } from "../components/atoms/Icons";
import type { Option } from "../lib/types";
import { labels } from "./OptionField";
export default function ParameterPanel({
  settings,
  field,
}: {
  settings: Option[];
  field: (option: Option) => ReactNode;
}) {
  const [group, setGroup] = useState(""),
    [query, setQuery] = useState("");
  const groups = [...new Set(settings.map((o) => o.group))];
  const selectedGroup = groups.includes(group) ? group : groups[0];
  const visible = settings.filter((o) =>
    query
      ? `${labels[o.name] || o.label} ${o.help} ${o.flag}`
          .toLowerCase()
          .includes(query.toLowerCase())
      : o.group === selectedGroup,
  );
  return (
    <>
      {settings.length ? (
        <>
          <label className="search-field option-search">
            <Search size={18} aria-hidden="true" />
            <input
              aria-label="Cari parameter"
              placeholder="Cari parameter atau argumen CLI…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div className="option-workspace">
            <div className="option-groups" aria-label="Kategori parameter">
              {groups.map((g) => (
                <button
                  type="button"
                  key={g}
                  aria-pressed={!query && g === selectedGroup}
                  onClick={() => {
                    setGroup(g);
                    setQuery("");
                  }}
                >
                  {g === "options" ? "Umum" : g}
                  <small>{settings.filter((o) => o.group === g).length}</small>
                </button>
              ))}
            </div>
            <div className="option-fields">
              <h3>
                {query
                  ? `Hasil pencarian (${visible.length})`
                  : selectedGroup === "options"
                    ? "Pengaturan umum"
                    : selectedGroup}
              </h3>
              <div className="form-grid">{visible.map(field)}</div>
              {!visible.length && (
                <p>
                  Tidak ada parameter yang cocok. Coba nama argumen seperti dpi
                  atau seed.
                </p>
              )}
            </div>
          </div>
        </>
      ) : (
        <p>Alur ini menggunakan konfigurasi tersimpan dari run sumber.</p>
      )}
      <Disclosure className="managed-options">
        <summary>Pengaturan yang dikelola server</summary>
        <p>
          Folder output dibuat per eksperimen. Lokasi Vina, OpenBabel, dan
          BIOVIA mengikuti instalasi server. Verifikasi TLS selalu aktif, dan
          progres ditampilkan melalui UI. Opsi ilmiah lain tersedia pada
          kategori di atas.
        </p>
      </Disclosure>
    </>
  );
}
