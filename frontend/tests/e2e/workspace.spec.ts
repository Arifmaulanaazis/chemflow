import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const password = "chemflow-e2e-local-password";
async function login(page: any) {
  await page.goto("/");
  await page.getByLabel("Kata sandi ruang kerja").fill(password);
  await page.getByRole("button", { name: "Masuk", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Ruang kerja", exact: true }),
  ).toBeVisible();
}
test("login, accessible workspace, real CLI job, table, download, navigation", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await expect(page.getByText("Pemantauan langsung")).toBeVisible();
  let result = await new AxeBuilder({ page }).analyze();
  expect(result.violations).toEqual([]);
  await page.screenshot({
    path: `../.cache/webui-${info.project.name}.png`,
    fullPage: info.project.name !== "mobile",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Eksperimen baru", exact: true })
    .click();
  await page.getByRole("button", { name: /^Template input/ }).click();
  await page
    .getByLabel("Nama eksperimen")
    .fill(`Template ${info.project.name} ${Date.now()}`);
  await page.getByRole("button", { name: "Lanjutkan", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Siapkan bahan eksperimen." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Lanjutkan", exact: true }).click();
  await page.getByLabel("Lewati pemeriksaan dependensi").check();
  await page.getByRole("button", { name: "Lanjutkan", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Siap memulai eksperimen?" }),
  ).toBeVisible();
  await page.screenshot({
    path: `../.cache/webui-review-${info.project.name}.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Jalankan eksperimen" }).click();
  await expect(page.locator(".badge.succeeded")).toBeVisible({
    timeout: 90000,
  });
  await page
    .getByRole("button")
    .filter({ hasText: "ligan_contoh_tidy.xlsx" })
    .click();
  await expect(page.locator(".artifact-preview table")).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Unduh", exact: true }).click();
  expect((await downloadPromise).suggestedFilename()).toContain(".xlsx");
  await page.getByRole("tab", { name: "Aktivitas & log" }).click();
  await expect(page.getByLabel("Log pipeline")).toContainText("Template Excel");
  result = await new AxeBuilder({ page }).analyze();
  expect(result.violations).toEqual([]);
  await page.screenshot({
    path: `../.cache/webui-results-${info.project.name}.png`,
    fullPage: true,
  });
  await page.getByRole("link", { name: "Mesin & sumber daya" }).click();
  await expect(
    page.getByRole("heading", { name: "Mesin & sumber daya" }),
  ).toBeVisible();
  if (info.project.name === "mobile")
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
  await page.getByRole("link", { name: "Panduan", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Kenali ruang kerja Anda" }),
  ).toBeVisible();
  if (info.project.name === "mobile")
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
  await page.getByRole("button", { name: "Keluar", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Masuk", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
test("upload validation, receptor builder, NGL viewer and geometric controls", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await page.getByRole("link", { name: /^Viewer test fixture/ }).click();
  await page.getByRole("button").filter({ hasText: "fixture.pdb" }).click();
  await expect(page.getByText("Memuat struktur molekul…")).toBeHidden({
    timeout: 60000,
  });
  await expect(page.locator(".molecule-canvas canvas")).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByRole("combobox", { name: "Representasi molekul" }).click();
  await page.getByRole("option", { name: "Ball & stick", exact: true }).click();
  await page.getByLabel("Kontak geometrik NGL").check();
  await page.getByLabel("Gridbox", { exact: true }).check();
  await expect(page.getByLabel("Center X (Å)", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Fit", exact: true }).click();
  await page.screenshot({
    path: `../.cache/webui-molecule-${info.project.name}.png`,
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.goto("/#new");
  await expect(
    page.getByRole("heading", { name: "Eksperimen baru" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Lanjutkan", exact: true }).click();
  await page.getByLabel("Unggah Workbook ligan").setInputFiles({
    name: "invalid.exe",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("invalid"),
  });
  await expect(page.getByRole("alert")).toContainText("format");
  await page
    .getByText("Buat workbook reseptor di browser", { exact: true })
    .click();
  await page.getByLabel("Kode PDB", { exact: true }).fill("1HSG");
  await page.getByRole("button", { name: "Tambahkan situs" }).click();
  await page.getByRole("button", { name: "Gunakan workbook 1 situs" }).click();
  await expect(page.locator("#option-receptors")).toContainText(
    "reseptor.xlsx",
  );
  expect(errors).toEqual([]);
});

test("guided inputs, draft preservation, CLI parameter search, review and adaptive navigation", async ({
  page,
}, info) => {
  await login(page);
  await page
    .getByRole("button", { name: "Eksperimen baru", exact: true })
    .click();
  await page.getByLabel("Nama eksperimen").fill("Wizard browser verification");
  await page.getByRole("button", { name: "Lanjutkan", exact: true }).click();
  await page.getByRole("button", { name: "Lanjutkan", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("reseptor");
  await page
    .getByText("Tulis ligan langsung di browser", { exact: true })
    .click();
  await page.getByLabel("Nama senyawa 1", { exact: true }).fill("Ethanol");
  await page.getByLabel("SMILES senyawa 1", { exact: true }).fill("CCO");
  await page.getByRole("button", { name: "Gunakan 1 senyawa" }).click();
  await expect(page.locator("#option-ligands")).toContainText("ligan.xlsx");
  await page
    .getByText("Buat workbook reseptor di browser", { exact: true })
    .click();
  await page.getByLabel("Kode PDB", { exact: true }).fill("1HSG");
  await page.getByRole("button", { name: "Tambahkan situs" }).click();
  await page.getByRole("button", { name: "Gunakan workbook 1 situs" }).click();
  await expect(page.locator("#option-receptors")).toHaveValue(
    /\/reseptor.xlsx$/,
  );
  await page.getByRole("button", { name: "Lanjutkan", exact: true }).click();
  await page.getByLabel("Cari parameter").fill("exhaustiveness");
  await page.getByLabel("Kedalaman pencarian", { exact: true }).fill("16");
  await page.getByLabel("Cari parameter").fill("figure-formats");
  await page.getByLabel("svg", { exact: true }).check();
  await page.getByRole("button", { name: "Lanjutkan", exact: true }).click();
  await expect(page.locator(".review-list")).toContainText("ligan.xlsx");
  await expect(page.locator(".review-list")).toContainText("reseptor.xlsx");
  await expect(page.locator(".review-list")).toContainText("16");
  await expect(page.locator(".review-list")).toContainText("svg");
  const axe = await new AxeBuilder({ page }).analyze();
  expect(axe.violations).toEqual([]);
  if (info.project.name === "mobile") {
    for (const viewport of [
      { width: 375, height: 812 },
      { width: 844, height: 390 },
      { width: 768, height: 1024 },
    ]) {
      await page.setViewportSize(viewport);
      const nav = page.getByRole("navigation", { name: "Navigasi mobile" });
      await expect(nav).toBeVisible();
      const rect = await nav.boundingBox();
      expect(rect!.y + rect!.height).toBeLessThan(viewport.height);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
    await page.setViewportSize({ width: 390, height: 844 });
  } else
    await expect(
      page.getByRole("navigation", { name: "Navigasi mobile" }),
    ).toBeHidden();
  await page.screenshot({
    path: `../.cache/webui-wizard-${info.project.name}.png`,
    fullPage: true,
  });
  await page.goto("/#overview");
  await page
    .getByRole("button", { name: "Eksperimen baru", exact: true })
    .click();
  await expect(page.getByLabel("Nama eksperimen")).toHaveValue(
    "Wizard browser verification",
  );
});

test("mobile menu focus, GC-MS vector input and reduced motion", async ({
  page,
}, info) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await login(page);
  if (info.project.name === "mobile") {
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(
      page.getByRole("dialog", { name: "Ruang kerja Anda" }),
    ).toBeVisible();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
  }
  await page
    .getByRole("button", { name: "Eksperimen baru", exact: true })
    .click();
  await page.getByRole("button", { name: /Analisis GC-MS/ }).click();
  await page.getByRole("button", { name: "Lanjutkan", exact: true }).click();
  await page.getByLabel("Unggah Data GC-MS").setInputFiles({
    name: "chromatogram.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("rt,intensity\n1,2\n2,10\n3,4"),
  });
  await expect(page.locator("#option-data option:checked")).toContainText(
    "chromatogram.csv",
  );
  await page.getByRole("button", { name: "Lanjutkan", exact: true }).click();
  await page.getByLabel("Cari parameter").fill("rt-range");
  await page
    .getByLabel("Rentang waktu retensi (awal akhir)", { exact: true })
    .fill("1 20");
  await page.getByRole("button", { name: "Lanjutkan", exact: true }).click();
  await expect(page.locator(".review-list")).toContainText("1 20");
  await page.getByRole("button", { name: /Bahan eksperimen/ }).click();
  await expect(
    page.getByRole("heading", { name: "Siapkan bahan eksperimen." }),
  ).toBeVisible();
  await page.getByRole("button", { name: /4 Tinjau & jalankan/ }).click();
  await expect(
    page.getByRole("heading", { name: "Siap memulai eksperimen?" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
