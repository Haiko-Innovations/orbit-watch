import AxeBuilder from "@axe-core/playwright";
import { type Browser, expect, type Page, test } from "@playwright/test";
import { asParty, stackInfo } from "./stack";
import { installTestWallet, localTestKey } from "./testWallet";

// The accessibility review of every view (phase 3, step 3.8; docs/accessibility.md), against
// the local stack. Each view is opened as the role that uses it, and checked:
//
// - with axe (WCAG 2.0, 2.1 and 2.2, levels A and AA) in light and dark colours;
// - at 320 CSS pixels wide (WCAG 1.4.10, reflow), for sideways scrolling;
// - with the keyboard alone: Tab reaches everything, in order, with a visible focus
//   indicator and no trap, and the skip link takes focus to the page's heading.
//
// It only reads: the role tests change the stack. Everything is LOCAL and SIMULATED.

const REQUESTER = "requester:sim-cubesat-team";
const STATION = "station:SIM-ESPOO";

interface View {
  name: string;
  path: string | (() => Promise<string>);
  heading: string | RegExp;
  party?: string;
}

async function reviewTask(browser: Browser): Promise<string> {
  const reviewer = (stackInfo() as unknown as { in_review: { reviewers: string[] } }).in_review
    .reviewers[2];
  const context = await browser.newContext();
  const tasks = (await asParty(context.request, reviewer ?? "", "GET", "/v1/tasks")).json.tasks as {
    task_id: string;
  }[];
  await context.close();
  return `/#/tasks/${tasks[0]?.task_id ?? "none"}`;
}

function views(browser: Browser): View[] {
  const reviewer = (stackInfo() as unknown as { in_review: { reviewers: string[] } }).in_review
    .reviewers[2];
  return [
    { name: "Network", path: "/#/", heading: "Network" },
    { name: "Open requests", path: "/#/requests", heading: "Open requests" },
    { name: "Attestations", path: "/#/attestations", heading: "Attestations" },
    { name: "Station quality meter", path: "/#/quality", heading: "Station quality meter" },
    { name: "Sign in", path: "/#/sign-in", heading: "Sign in" },
    { name: "Page not found", path: "/#/nowhere", heading: "Page not found" },
    { name: "Your account", path: "/#/account", heading: "Your account", party: REQUESTER },
    { name: "Your requests", path: "/#/my-requests", heading: "Your requests", party: REQUESTER },
    { name: "New request", path: "/#/new-request", heading: "New request", party: REQUESTER },
    {
      name: "A request, for its requester",
      path: "/#/requests/SIM-REQ-3001",
      heading: /SIMULATED/,
      party: REQUESTER,
    },
    {
      name: "A settled request, for its observer",
      path: "/#/requests/SIM-REQ-3000",
      heading: /SIMULATED/,
      party: STATION,
    },
    {
      name: "Open requests, for a station",
      path: "/#/requests",
      heading: "Open requests",
      party: STATION,
    },
    { name: "Your station", path: "/#/station", heading: "Your station", party: STATION },
    {
      name: "Your observations",
      path: "/#/my-observations",
      heading: "Your observations",
      party: STATION,
    },
    {
      name: "Your review tasks",
      path: "/#/tasks",
      heading: "Your review tasks",
      party: reviewer ?? "",
    },
    {
      name: "A review task",
      path: () => reviewTask(browser),
      heading: "Review task",
      party: reviewer ?? "",
    },
    { name: "Administration", path: "/#/admin", heading: "Administration", party: "admin" },
  ];
}

async function open(browser: Browser, view: View): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  if (view.party) {
    const party = view.party === "admin" ? stackInfo().admin.party : view.party;
    await installTestWallet(page, localTestKey(party));
    await page.goto("/#/sign-in");
    await page.getByRole("button", { name: "Test wallet (LOCAL keys)" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();
  }
  const path = typeof view.path === "string" ? view.path : await view.path();
  // A fresh load, so that the keyboard starts at the top of the page.
  await page.goto("about:blank");
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1, name: view.heading })).toBeVisible();
  await expect(page.getByText("Loading…")).toHaveCount(0);
  return page;
}

interface Focused {
  tag: string;
  text: string;
  visible: boolean;
  indicator: boolean;
  inside: boolean;
}

function focused(page: Page): Promise<Focused> {
  return page.evaluate(() => {
    const element = document.activeElement as HTMLElement | null;
    if (!element || element === document.body) {
      return { tag: "BODY", text: "", visible: false, indicator: false, inside: false };
    }
    const style = getComputedStyle(element);
    const box = element.getBoundingClientRect();
    const label =
      element.getAttribute("aria-label") ||
      (element as HTMLInputElement).labels?.[0]?.textContent ||
      element.textContent ||
      element.getAttribute("name") ||
      "";
    return {
      tag: element.tagName,
      text: label.trim().slice(0, 60),
      visible: box.width > 0 && box.height > 0,
      indicator:
        (style.outlineStyle !== "none" && Number.parseFloat(style.outlineWidth) >= 2) ||
        style.boxShadow !== "none",
      inside: document.body.contains(element),
    };
  });
}

/** Tab from the top to the end: every stop visible, with a focus indicator; no trap. */
async function walk(page: Page, view: string): Promise<number> {
  const stops: string[] = [];
  for (let i = 0; i < 300; i += 1) {
    await page.keyboard.press("Tab");
    const now = await focused(page);
    if (now.tag === "BODY" || (i > 0 && now.text === "Skip to content")) return stops.length;
    if (i === 0) expect(now.text, `${view}: the first stop`).toBe("Skip to content");
    expect(now.visible, `${view}: ${now.tag} "${now.text}" is focused but not shown`).toBe(true);
    expect(now.indicator, `${view}: ${now.tag} "${now.text}" shows no focus`).toBe(true);
    stops.push(`${now.tag} ${now.text}`);
  }
  throw new Error(`${view}: Tab never left the page: ${stops.slice(-5).join(" | ")}`);
}

async function audit(page: Page, view: string) {
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(result.violations, `${view}, ${colorScheme} colours`).toEqual([]);
  }
  await page.emulateMedia({ colorScheme: "light" });
}

test("every view passes axe, fits a phone and works with the keyboard alone", async ({
  browser,
}) => {
  test.setTimeout(300_000);
  const reviewed: string[] = [];
  for (const view of views(browser)) {
    const page = await open(browser, view);
    const stops = await walk(page, view.name);
    expect(stops, `${view.name}: nothing to reach by keyboard`).toBeGreaterThan(3);

    // The skip link takes keyboard and screen reader users to the page's heading.
    await page.goto("about:blank");
    await page.goBack();
    await expect(page.getByRole("heading", { level: 1, name: view.heading })).toBeVisible();
    await page.keyboard.press("Tab");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1, name: view.heading })).toBeFocused();

    await audit(page, view.name);
    // WCAG 1.4.10 (reflow): 320 CSS pixels wide, no scrolling in two directions.
    await page.setViewportSize({ width: 320, height: 800 });
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width, `${view.name}: sideways scrolling at 320 pixels`).toBeLessThanOrEqual(320);
    await page.context().close();
    reviewed.push(`${view.name}: ${stops} keyboard stops`);
  }
  test.info().annotations.push({ type: "reviewed", description: reviewed.join("; ") });
  console.log(`Reviewed:\n${reviewed.join("\n")}`);
});
