import type { Upload } from "./types";

const tables = ["xlsx", "xls", "csv", "tsv", "txt"];
export function inputExtensions(name: string): string[] {
  if (["ligands", "receptors"].includes(name)) return ["xlsx", "xls"];
  if (["data", "gcms"].includes(name)) return [...tables, "cdf", "mzml", "mzxml"];
  if (["library", "gcms_library"].includes(name)) return [...tables, "json"];
  return tables;
}
export function inputUploads(uploads: Upload[], name: string, value: unknown) {
  const selected = new Set(Array.isArray(value) ? value : [value]);
  const compatible = uploads.filter((file) =>
    selected.has(file.id) || ((!file.purpose || file.purpose === name) &&
      inputExtensions(name).includes(file.name.split(".").pop()!.toLowerCase())));
  const byName = new Map<string, Upload>();
  for (const file of compatible) {
    const key = file.name.toLowerCase();
    const previous = byName.get(key);
    if (!previous || !selected.has(previous.id)) byName.set(key, file);
  }
  return compatible.filter((file, index) =>
    compatible.findIndex((other) => other.id === file.id) === index &&
    (selected.has(file.id) || byName.get(file.name.toLowerCase())?.id === file.id));
}
