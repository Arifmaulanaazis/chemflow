import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
async function login(page: any) {
  await page.goto("/");
  await page
    .getByLabel("Kata sandi ruang kerja")
    .fill("chemflow-e2e-local-password");
  await page.getByRole("button", { name: "Masuk", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Ruang kerja", exact: true }),
  ).toBeVisible();
}

test("official logo, looping molecule fits mobile, custom dropdown keyboard and workshop reader", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await expect(
    page.locator(".brand-mark").filter({ visible: true }).first(),
  ).toHaveAttribute("src", "/chemflow.png");
  const molecule = page.locator(".hero-molecule-viewport");
  await expect(page.locator(".hero-molecule")).toHaveAttribute("data-state","ready");
  await expect(page.getByText("Geser untuk memutar · cubit untuk zoom",{exact:true})).toHaveCount(0);
  const canvas = molecule.locator("canvas");
  await expect(canvas).toBeVisible();
  expect(await canvas.evaluate((el:any)=>!!el.getContext("webgl2"))).toBe(true);
  const first = await canvas.screenshot();
  await page.waitForTimeout(350);
  expect((await canvas.screenshot()).equals(first)).toBe(false);
  const hero = await page.locator(".discovery-hero").boundingBox(), visual = await molecule.boundingBox();
  expect(visual!.x).toBeGreaterThanOrEqual(hero!.x);
  expect(visual!.x + visual!.width).toBeLessThanOrEqual(hero!.x + hero!.width);
  expect(visual!.y + visual!.height).toBeLessThanOrEqual(hero!.y + hero!.height);
  const box=await canvas.boundingBox();
  await page.mouse.move(box!.x+box!.width*.45,box!.y+box!.height*.5);
  await page.mouse.down();
  await page.mouse.move(box!.x+box!.width*.8,box!.y+box!.height*.7,{steps:10});
  await page.mouse.up();
  const dragged = await canvas.screenshot();
  expect(dragged.equals(first)).toBe(false);
  await molecule.focus();
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("+");
  await page.waitForTimeout(100);
  expect((await canvas.screenshot()).equals(dragged)).toBe(false);
  await page.keyboard.press("r");
  await expect(page.getByRole("button",{name:/Jeda animasi|Putar animasi/})).toHaveCount(0);
  if(info.project.name === "mobile") {
    const session=await page.context().newCDPSession(page);
    const x=box!.x+box!.width*.5,y=box!.y+box!.height*.5;
    await session.send("Input.dispatchTouchEvent",{type:"touchStart",touchPoints:[{x,y}]});
    await session.send("Input.dispatchTouchEvent",{type:"touchMove",touchPoints:[{x:x+55,y:y-20}]});
    await session.send("Input.dispatchTouchEvent",{type:"touchEnd",touchPoints:[]});
    await session.send("Input.dispatchTouchEvent",{type:"touchStart",touchPoints:[{x:x-35,y,id:1},{x:x+35,y,id:2}]});
    await session.send("Input.dispatchTouchEvent",{type:"touchMove",touchPoints:[{x:x-50,y,id:1},{x:x+50,y,id:2}]});
    await session.send("Input.dispatchTouchEvent",{type:"touchEnd",touchPoints:[]});
    await session.detach();
    await molecule.focus();await page.keyboard.press("r");
  }
  await molecule.evaluate(el=>(el as HTMLElement).blur());
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({
    path: `../.cache/interactive-home-${info.project.name}.png`,
    fullPage: info.project.name !== "mobile",
  });
  await page.goto("/#library");
  await expect(
    page.getByRole("heading", { name: "Materi & sitasi", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Merender halaman materi…")).toBeHidden({
    timeout: 60000,
  });
  await expect(page.locator(".pdf-scroll canvas")).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Halaman materi" }),
  ).toContainText("1 / 56");
  await page.getByRole("button", { name: "Berikutnya", exact: true }).click();
  await expect(
    page.getByRole("combobox", { name: "Halaman materi" }),
  ).toContainText("2 / 56");
  await page.getByRole("combobox", { name: "Halaman materi" }).focus();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Home");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("combobox", { name: "Halaman materi" }),
  ).toContainText("3 / 56");
  await expect(page.getByText("Merender halaman materi…")).toBeHidden({
    timeout: 60000,
  });
  await page.getByRole("combobox",{name:"Halaman materi"}).click();
  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("combobox",{name:"Halaman materi"})).toContainText("56 / 56");
  await expect(page.locator(".pdf-reader .sr-only")).toContainText("Runtime baru",{timeout:60000});
  await expect(page.locator(".citation-list li")).toHaveCount(8);
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "BibTeX", exact: true }).click();
  expect((await download).suggestedFilename()).toContain(".bib");
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await expect(page.getByText("Merender halaman materi…")).toBeHidden();
  await page.locator(".library-panel").screenshot({path:`../.cache/interactive-library-${info.project.name}.png`});
  expect(errors).toEqual([]);
});

test("real RCSB receptor, native ligand and controlled NGL bounding box", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await page.goto("/#new");
  await page.getByRole("button", { name: "Lanjutkan", exact: true }).click();
  await page
    .getByText("Buat workbook reseptor di browser", { exact: true })
    .click();
  await page.getByLabel("Kode PDB", { exact: true }).fill("1HSG");
  await page
    .getByRole("button", { name: "Cari ligan native", exact: true })
    .click();
  await expect(page.getByText("Memuat reseptor dan ligan native…")).toBeHidden({
    timeout: 60000,
  });
  await expect(page.locator(".target-canvas canvas")).toBeVisible();
  const response = await page.request.get("/api/receptors/1HSG");
  expect(response.ok()).toBe(true);
  const metadata = await response.json();
  expect(metadata.ligands.length).toBeGreaterThan(0);
  const native = metadata.ligands[0];
  await expect(page.locator(".target-canvas")).toHaveAttribute(
    "data-native",
    native.label,
  );
  await page.getByRole("button", { name: "Fokus situs", exact: true }).click();
  await page.waitForTimeout(650);
  const image = await page.locator(".target-canvas").screenshot();
  const x = native.center[0] + 5;
  await page.locator("#receptor-0").fill(String(x));
  await page.locator("#receptor-3").fill("24");
  await expect
    .poll(async () => {
      const vertices = JSON.parse(
        (await page
          .locator(".target-canvas")
          .getAttribute("data-box-vertices"))!,
      );
      return Math.min(...vertices.map((v: number[]) => v[0]));
    })
    .toBeCloseTo(x - 12, 3);
  await page.waitForTimeout(250);
  expect(
    (await page.locator(".target-canvas").screenshot()).equals(image),
  ).toBe(false);
  await page
    .getByRole("combobox", { name: "Ligan native", exact: true })
    .click();
  await page
    .getByRole("option", { name: "Koordinat manual", exact: true })
    .click();
  await expect(page.locator(".target-canvas")).toHaveAttribute(
    "data-native",
    "manual",
  );
  await page
    .getByRole("combobox", { name: "Ligan native", exact: true })
    .click();
  await page.getByRole("option", { name: new RegExp(native.label) }).click();
  await expect(page.locator("#receptor-0")).toHaveValue(
    String(native.center[0]),
  );
  await page.screenshot({
    path: `../.cache/interactive-gridbox-${info.project.name}.png`,
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});

test("workbook preview becomes an interactive chart with source values and SVG export", async ({
  page,
}, info) => {
  await login(page);
  await page.getByRole("link", { name: /^Viewer test fixture/ }).click();
  await page.getByRole("button").filter({ hasText: "affinity.csv" }).click();
  await page
    .getByRole("button", { name: "Grafik interaktif", exact: true })
    .click();
  await expect(page.locator(".live-chart")).toBeVisible();
  await page.locator(".live-chart g[role=button]").first().focus();
  await expect(page.locator(".chart-tooltip")).toContainText("Alpha");
  await expect(page.locator(".chart-tooltip")).toContainText("-7,2");
  await page.getByRole("combobox", { name: "Jenis grafik" }).click();
  await page.getByRole("option", { name: "Garis", exact: true }).click();
  await expect(page.locator(".live-chart circle")).toHaveCount(3);
  await page.getByRole("combobox", { name: "Seri grafik" }).click();
  await page.getByRole("option", { name: "replicate", exact: true }).click();
  await page.locator(".live-chart g[role=button]").first().focus();
  await expect(page.locator(".chart-tooltip")).toContainText("replicate: 1");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Unduh SVG", exact: true }).click();
  expect((await download).suggestedFilename()).toBe("chemflow-chart.svg");
  await page.screenshot({
    path: `../.cache/interactive-chart-${info.project.name}.png`,
    fullPage: true,
  });
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});


test("hero WebGL fallback and remount do not break the workspace",async({page})=>{
  const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
  await login(page);
  await expect(page.locator(".hero-molecule")).toHaveAttribute("data-state","ready");
  await page.locator(".hero-molecule canvas").evaluate((el:any)=>el.getContext("webgl2").getExtension("WEBGL_lose_context").loseContext());
  await expect(page.getByText("Pratinjau 3D memerlukan WebGL pada browser ini.")).toBeVisible();
  await page.goto("/#resources");
  await expect(page.getByRole("heading",{name:"Mesin & sumber daya",exact:true})).toBeVisible();
  await page.goto("/#overview");
  await expect(page.locator(".hero-molecule")).toHaveAttribute("data-state","ready");
  await expect(page.locator(".hero-molecule canvas")).toHaveCount(1);
  expect(errors).toEqual([]);
});
