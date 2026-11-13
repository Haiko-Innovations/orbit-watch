import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { generatePrivateKey, privateKeyToAccount } from "viem/accounts";
import { installTestWallet, localTestKey } from "./testWallet";

// Signing in with a wallet (phase 3, step 3.2), against the local stack. The wallets hold
// LOCAL TEST keys; the chain has no value.

const ORIGIN = "http://127.0.0.1:8790";

async function audit(page: Page) {
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(result.violations, `${colorScheme} colours`).toEqual([]);
  }
}

async function chooseTestWallet(page: Page) {
  await page.goto("/#/sign-in");
  await page.getByRole("button", { name: "Test wallet (LOCAL keys)" }).click();
}

test("a station with a registered wallet signs in and out", async ({ page, context }) => {
  const address = await installTestWallet(page, localTestKey("station:SIM-ESPOO"));
  await page.goto("/#/sign-in");
  await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
  await audit(page);
  await page.getByRole("button", { name: "Test wallet (LOCAL keys)" }).click();

  await expect(page.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();
  await expect(page.locator("dl.details")).toContainText("station:SIM-ESPOO");
  await expect(page.locator("dl.details")).toContainText("Observer station");
  await expect(page.locator("dl.details")).toContainText(address);
  await expect(page.getByRole("link", { name: "station:SIM-ESPOO" })).toBeVisible();
  await audit(page);

  // The session is a cookie that scripts cannot read; nothing secret is in the page.
  const [cookie] = await context.cookies();
  expect(cookie).toMatchObject({ name: "ow_session", httpOnly: true, sameSite: "Strict" });
  const visible = await page.evaluate(() => ({
    cookie: document.cookie,
    local: Object.keys(localStorage).length,
    session: Object.keys(sessionStorage).length,
  }));
  expect(visible).toEqual({ cookie: "", local: 0, session: 0 });
  expect(await page.content()).not.toContain(cookie?.value ?? "missing");

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Network" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
  const after = await page.request.get("/v1/session");
  expect(await after.json()).toEqual({ session: null });
});

test("a new wallet signs up as an observer station", async ({ page }) => {
  await installTestWallet(page, generatePrivateKey());
  await chooseTestWallet(page);
  await expect(page.getByRole("heading", { name: "Sign up" })).toBeFocused();
  await audit(page);
  // On a phone the long wallet address wraps instead of widening the page.
  await page.setViewportSize({ width: 360, height: 800 });
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(width).toBeLessThanOrEqual(360);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.getByLabel("an observer: I run a station").check();
  await page.getByLabel("Name").fill("SIM-TEST-STATION");
  await expect(page.getByText("Your account will be station:SIM-TEST-STATION.")).toBeVisible();
  await page.getByRole("button", { name: "Sign up and sign in" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();
  await expect(page.locator("dl.details")).toContainText("station:SIM-TEST-STATION");
});

test("a name that is taken is refused, and nothing is signed", async ({ page }) => {
  await installTestWallet(page, generatePrivateKey());
  await chooseTestWallet(page);
  await page.getByLabel("a requester: I ask for observations").check();
  await page.getByLabel("Name").fill("sim-cubesat-team");
  await page.getByRole("button", { name: "Sign up and sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("requester:sim-cubesat-team already exists");
});

test("declining in the wallet signs nobody in", async ({ page, context }) => {
  await installTestWallet(page, localTestKey("requester:sim-cubesat-team"), { decline: true });
  await chooseTestWallet(page);
  await expect(page.getByRole("alert")).toContainText("You declined in your wallet.");
  expect(await context.cookies()).toEqual([]);
  await page.getByRole("button", { name: "Choose a wallet again" }).click();
  await expect(page.getByRole("button", { name: "Test wallet (LOCAL keys)" })).toBeVisible();
});

test("a sign-in message works once, for its own page only", async ({ request }) => {
  const account = privateKeyToAccount(localTestKey("station:SIM-OULU"));
  const ask = (origin: string) =>
    request.post("/v1/session/challenge", {
      data: { address: account.address },
      headers: { Origin: origin },
    });
  const foreign = await ask("https://evil.example");
  expect(foreign.status()).toBe(403);
  expect((await foreign.json()).error.code).toBe("forbidden_origin");

  const { message } = await (await ask(ORIGIN)).json();
  const signature = await account.signMessage({ message });
  const signIn = () =>
    request.post("/v1/session", { data: { message, signature }, headers: { Origin: ORIGIN } });
  expect((await signIn()).status()).toBe(200);
  const replayed = await signIn();
  expect((await replayed.json()).error.code).toBe("message_used");

  const changed = message.replace(ORIGIN, "https://evil.example");
  const forged = await request.post("/v1/session", {
    data: { message: changed, signature: await account.signMessage({ message: changed }) },
    headers: { Origin: ORIGIN },
  });
  expect((await forged.json()).error.code).toBe("unknown_message");
});
