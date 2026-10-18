import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import Login from "../src/features/Login";
import JobComposer from "../src/features/JobComposer";
import { Badge } from "../src/components/atoms";
import { bytes } from "../src/lib/api";
import type { Schema } from "../src/lib/types";
const schema: Schema = {
  version: "3.0.0",
  platform: "Linux",
  biovia: false,
  max_upload_mb: 100,
  commands: {
    run: [
      {
        name: "rmsd_only",
        label: "rmsd only",
        flag: "--rmsd-only",
        help: "Hanya validasi native",
        required: false,
        group: "RMSD",
        kind: "boolean",
        multiple: false,
        count: null,
        choices: null,
        default: false,
      },
    ],
    init: [],
  },
};
beforeEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
});
describe("authentication", () => {
  it("reveals and conceals the same credential without submitting",()=>{
    render(<Login onLogin={vi.fn()}/>);
    const input=screen.getByLabelText("Kata sandi ruang kerja");
    fireEvent.change(input,{target:{value:"keep-this-password"}});
    fireEvent.click(screen.getByRole("button",{name:"Tampilkan kata sandi"}));
    expect(input).toHaveAttribute("type","text");
    expect(input).toHaveValue("keep-this-password");
    fireEvent.click(screen.getByRole("button",{name:"Sembunyikan kata sandi"}));
    expect(input).toHaveAttribute("type","password");
  });

  it("shows API rejection without losing input", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: "Kata sandi tidak cocok." }),
      }),
    );
    render(<Login onLogin={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Kata sandi ruang kerja"), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Masuk" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Kata sandi tidak cocok.",
    );
    expect(screen.getByLabelText("Kata sandi ruang kerja")).toHaveValue(
      "wrong",
    );
  });
  it("submits credential and clears password on success", async () => {
    const onLogin = vi.fn();
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ csrf: "token" }),
    });
    vi.stubGlobal("fetch", fetch);
    render(<Login onLogin={onLogin} />);
    fireEvent.change(screen.getByLabelText("Kata sandi ruang kerja"), {
      target: { value: "correct-password" },
    });
    fireEvent.submit(
      screen.getByRole("button", { name: "Masuk" }).closest("form")!,
    );
    await waitFor(() => expect(onLogin).toHaveBeenCalledOnce());
    expect(JSON.parse(fetch.mock.calls[0][1].body).password).toBe(
      "correct-password",
    );
  });
});
describe("composer wizard", () => {
  it("keeps Windows-only automation unavailable and validates input before advancing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
    );
    render(
      <JobComposer
        schema={schema}
        jobs={[]}
        onBack={vi.fn()}
        onCreated={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: /Ekspor interaksi BIOVIA/ }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: "Lanjutkan", exact: true }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Siapkan bahan eksperimen." }),
      ).toBeVisible(),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Lanjutkan", exact: true }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent("reseptor");
  });
  it("creates a job only after the review step and preserves draft on errors", async () => {
    const fetch = vi.fn().mockImplementation((url: string) =>
      Promise.resolve(
        url.endsWith("/uploads")
          ? { ok: true, json: async () => [] }
          : {
              ok: false,
              status: 422,
              json: async () => ({ detail: "Antrean tidak tersedia" }),
            },
      ),
    );
    vi.stubGlobal("fetch", fetch);
    render(
      <JobComposer
        schema={schema}
        jobs={[]}
        onBack={vi.fn()}
        onCreated={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Template input/ }));
    fireEvent.change(screen.getByLabelText("Nama eksperimen"), {
      target: { value: "Draft A" },
    });
    for (let i = 0; i < 3; i++)
      fireEvent.click(
        screen.getByRole("button", { name: "Lanjutkan", exact: true }),
      );
    expect(fetch.mock.calls.some((c) => c[0].endsWith("/jobs"))).toBe(false);
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Siap memulai eksperimen?" }),
      ).toBeVisible(),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Jalankan eksperimen" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Antrean tidak tersedia",
    );
    expect(JSON.parse(sessionStorage.getItem("chemflow-wizard-v2")!).name).toBe(
      "Draft A",
    );
    fireEvent.click(screen.getByRole("button", { name: "Sebelumnya" }));
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Sesuaikan perhitungan Anda." }),
      ).toBeVisible(),
    );
  });
});
it("labels job states and formats scientific file sizes", () => {
  render(<Badge status="interrupted" />);
  expect(screen.getByText("Terhenti")).toBeVisible();
  expect(bytes(1024 ** 3)).toBe("1.0 GB");
  expect(bytes(500)).toBe("500 B");
});

it("configures a resumed run through review before starting a new job", async () => {
  const fetch = vi.fn().mockImplementation((url: string) =>
    Promise.resolve({
      ok: true,
      json: async () => (url.endsWith("/uploads") ? [] : { id: "resumed" }),
    }),
  );
  vi.stubGlobal("fetch", fetch);
  const created = vi.fn();
  const job = {
    id: "source-1",
    name: "Run A",
    command: "run",
    status: "interrupted",
    created: 0,
    started: null,
    finished: null,
    exit_code: null,
    stage: null,
  };
  render(
    <JobComposer
      schema={{ ...schema, commands: { ...schema.commands, resume: [] } }}
      jobs={[job]}
      preset={{ command: "resume", source: "source-1" }}
      onBack={vi.fn()}
      onCreated={created}
    />,
  );
  expect(screen.getByLabelText("Nama eksperimen")).toHaveValue(
    "Lanjutan Run A",
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Lanjutkan", exact: true }),
  );
  expect(
    screen.getByLabelText(/Run sumber/, { selector: "select" }),
  ).toHaveValue("source-1");
  fireEvent.click(
    screen.getByRole("button", { name: "Lanjutkan", exact: true }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Lanjutkan", exact: true }),
  );
  expect(created).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Jalankan eksperimen" }));
  await waitFor(() => expect(created).toHaveBeenCalledWith("resumed"));
  const call = fetch.mock.calls.find(([url]) => url.endsWith("/jobs"));
  expect(JSON.parse(call![1].body).source_run).toBe("source-1");
});
