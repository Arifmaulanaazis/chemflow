import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { it, expect, vi, afterEach } from "vitest";
import InputRequests from "../src/features/InputRequests";
import OptionField from "../src/features/OptionField";
import type { Option } from "../src/lib/types";
afterEach(() => vi.restoreAllMocks());
it("answers a runtime SMILES request with structured JSON", async () => {
  const fetch = vi.fn().mockImplementation((url: string, init: any) =>
    Promise.resolve({
      ok: true,
      json: async () =>
        init.method === "POST"
          ? { ok: true }
          : [
              {
                id: "p1",
                kind: "smiles",
                title: "Lengkapi SMILES",
                compound: "Ethanol",
              },
            ],
    }),
  );
  vi.stubGlobal("fetch", fetch);
  render(<InputRequests jobId="j1" running={true} />);
  fireEvent.change(await screen.findByLabelText("SMILES untuk Ethanol"), {
    target: { value: "CCO" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Kirim & lanjutkan proses" }),
  );
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(
        ([url, init]) =>
          url.endsWith("/inputs/p1") && JSON.parse(init.body).smiles === "CCO",
      ),
    ).toBe(true),
  );
  await waitFor(() =>
    expect(
      screen.queryByRole("heading", { name: "Lengkapi SMILES" }),
    ).not.toBeInTheDocument(),
  );
});
it("supports explicit skip after an invalid SMILES response", async () => {
  const fetch = vi.fn().mockImplementation((url: string, init: any) =>
    Promise.resolve(
      init.method === "POST" && JSON.parse(init.body).smiles
        ? {
            ok: false,
            status: 422,
            json: async () => ({ detail: "SMILES tidak valid" }),
          }
        : {
            ok: true,
            json: async () =>
              init.method === "POST"
                ? {}
                : [
                    {
                      id: "p2",
                      kind: "smiles",
                      title: "Isi struktur",
                      compound: "Unknown",
                    },
                  ],
          },
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(<InputRequests jobId="j1" running={true} />);
  fireEvent.change(await screen.findByLabelText("SMILES untuk Unknown"), {
    target: { value: "invalid" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Kirim & lanjutkan proses" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "SMILES tidak valid",
  );
  fireEvent.click(screen.getByRole("button", { name: "Lewati senyawa ini" }));
  await waitFor(() =>
    expect(
      screen.queryByRole("heading", { name: "Isi struktur" }),
    ).not.toBeInTheDocument(),
  );
});
it("keeps a fixed-length numeric vector editable before normalization", () => {
  const changed = vi.fn();
  const o = {
    name: "rt_range",
    label: "Rentang waktu",
    flag: "--rt-range",
    kind: "number",
    count: 2,
    multiple: true,
    help: "",
    group: "Signal",
    default: null,
    choices: null,
    required: false,
  } as Option;
  render(
    <OptionField
      option={o}
      value="1 "
      uploads={[]}
      onChange={changed}
      onUpload={vi.fn()}
    />,
  );
  fireEvent.change(screen.getByLabelText(/Rentang waktu retensi/), {
    target: { value: "1 20" },
  });
  expect(changed).toHaveBeenCalledWith("1 20");
});

it("prefills native coordinates and sends edited gridbox values", async () => {
  const prompt = {
    id: "grid-1",
    kind: "gridbox",
    title: "Situs docking",
    choices: [
      { label: "LIG A 1", atoms: 4, center: [1, 2, 3], size: [20, 20, 20] },
      { label: "NAT B 2", atoms: 6, center: [4, 5, 6], size: [22, 22, 22] },
    ],
  };
  const fetch = vi.fn().mockImplementation((url: string, init: any) =>
    Promise.resolve({
      ok: true,
      json: async () => (init.method === "POST" ? {} : [prompt]),
    }),
  );
  vi.stubGlobal("fetch", fetch);
  render(<InputRequests jobId="j1" running={true} />);
  fireEvent.click(
    await screen.findByRole("combobox", { name: "Ligan native" }),
  );
  fireEvent.click(screen.getByRole("option", { name: "NAT B 2 (6 atom)" }));
  expect(screen.getByLabelText("Center X (Å)")).toHaveValue(4);
  fireEvent.change(screen.getByLabelText("Size Z (Å)"), {
    target: { value: "25" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Kirim & lanjutkan proses" }),
  );
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(
        ([url, init]) =>
          url.endsWith("/inputs/grid-1") &&
          JSON.parse(init.body).native === "NAT B 2" &&
          JSON.parse(init.body).size[2] === 25,
      ),
    ).toBe(true),
  );
});
