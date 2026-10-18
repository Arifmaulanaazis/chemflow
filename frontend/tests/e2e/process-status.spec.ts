import { test, expect } from "@playwright/test";

test("navbar and progress track running, waiting and completed jobs", async ({page}, info) => {
  const job = { id:"status-fixture", name:"Active docking", command:"run", status:"running", created:1, started:1,
    finished:null, exit_code:null, stage:"docking", pending_input:false };
  const jobs = [job, {...job,id:"queued-fixture",name:"Queued docking",status:"queued",started:null}];
  await page.route("**/api/events", route => route.fulfill({status:200,contentType:"text/event-stream",body:"retry: 60000\n\n"}));
  await page.route("**/api/jobs", route => route.fulfill({json:jobs}));
  await page.route("**/api/jobs/status-fixture/artifacts", route => route.fulfill({json:[]}));
  await page.route("**/api/jobs/status-fixture/logs", route => route.fulfill({json:{text:"Docking"}}));
  await page.route("**/api/jobs/status-fixture/inputs", route => route.fulfill({json:[]}));
  await page.goto("/");
  await page.getByLabel("Kata sandi ruang kerja").fill("chemflow-e2e-local-password");
  await page.getByRole("button",{name:"Masuk",exact:true}).click();
  const badge=page.locator(".run-status-badge");
  await expect(badge).toContainText("1 berjalan");
  await expect(badge).toContainText("1 antre");
  await badge.click();
  await page.getByRole("link",{name:/^Active docking/}).click();
  await expect(page.getByRole("progressbar")).toHaveAttribute("aria-valuetext","docking");
  await expect(page.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
  if(info.project.name === "mobile") await expect(page.locator(".bottom-nav .nav-count")).toHaveText("2");
  await page.screenshot({path:`../.cache/process-status-${info.project.name}.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.emulateMedia({reducedMotion:"reduce"});
  expect(await page.locator(".run-progress-track > span").evaluate(el=>getComputedStyle(el).animationName)).toBe("none");
  jobs[0] = {...job,pending_input:true};
  await page.reload();
  await expect(page.getByRole("progressbar")).toHaveClass(/waiting/);
  jobs[0] = {...job,status:"succeeded"};
  await page.reload();
  await expect(page.getByRole("progressbar")).toHaveAttribute("aria-valuenow","100");
  await expect(badge).not.toContainText("berjalan");
  await expect(badge).toContainText("1 antre");
});
