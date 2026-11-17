import { expect, test } from "@playwright/test";

// The privacy notice and the terms of use (phase 4, step 4.4; decision P4-09): linked from
// every page, and readable without signing in, even when the service does not answer. The
// accessibility review of these pages is in a11y.spec.ts.

const pages = [
  { path: "/#/privacy", heading: "Privacy notice" },
  { path: "/#/terms", heading: "Terms of use" },
];

for (const { path, heading } of pages) {
  test(`${heading} reads without signing in`, async ({ page }) => {
    await page.goto(path);
    const title = page.getByRole("heading", { level: 1, name: heading });
    await expect(title).toBeVisible();
    await expect(page).toHaveTitle(`${heading} · Orbit Watch`);
    await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible(); // nobody is
    await expect(page.locator("article.legal")).toContainText("Haiko Innovations Oy");
  });
}

test("the notice and the terms need no service at all", async ({ page }) => {
  await page.route("**/v1/**", (route) => route.abort());
  await page.goto("/#/terms");
  await expect(page.getByRole("heading", { level: 1, name: "Terms of use" })).toBeVisible();
  await expect(page.locator("article.legal")).toContainText("no value");
});

test("every page links to both, and the links lead there", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Network" })).toBeVisible();
  const legal = page.getByRole("navigation", { name: "Privacy and terms" });
  await expect(legal.getByRole("link")).toHaveText(["Privacy notice", "Terms of use"]);

  await legal.getByRole("link", { name: "Privacy notice" }).click();
  await expect(page).toHaveURL(/#\/privacy$/);
  await expect(page.getByRole("heading", { level: 1, name: "Privacy notice" })).toBeFocused();
  // The notice links to the terms, and focus moves to their heading.
  await page.locator("article.legal").getByRole("link", { name: "terms of use" }).click();
  await expect(page).toHaveURL(/#\/terms$/);
  await expect(page.getByRole("heading", { level: 1, name: "Terms of use" })).toBeFocused();
});

test("the old addresses of translations are not found", async ({ page }) => {
  await page.goto("/#/privacy/fi");
  await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
});
