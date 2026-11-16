import { expect, test } from "@playwright/test";

// The privacy notice and the terms of use (phase 4, step 4.4; decision P4-09): in English and
// Finnish, linked from every page, and readable without signing in, even when the service
// does not answer. The accessibility review of these pages is in a11y.spec.ts.

const pages = [
  { path: "/#/privacy", lang: "en", heading: "Privacy notice", other: "Suomeksi" },
  { path: "/#/privacy/fi", lang: "fi", heading: "Tietosuojaseloste", other: "In English" },
  { path: "/#/terms", lang: "en", heading: "Terms of use", other: "Suomeksi" },
  { path: "/#/terms/fi", lang: "fi", heading: "Käyttöehdot", other: "In English" },
];

for (const { path, lang, heading, other } of pages) {
  test(`${heading} reads without signing in, in its own language`, async ({ page }) => {
    await page.goto(path);
    const title = page.getByRole("heading", { level: 1, name: heading });
    await expect(title).toBeVisible();
    await expect(page.locator("article.legal")).toHaveAttribute("lang", lang);
    await expect(page).toHaveTitle(`${heading} · Orbit Watch`);
    await expect(page.getByRole("link", { name: other })).toBeVisible();
    await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible(); // nobody is
    await expect(page.locator("article.legal")).toContainText("Haiko Innovations Oy");
  });
}

test("the notice and the terms need no service at all", async ({ page }) => {
  await page.route("**/v1/**", (route) => route.abort());
  await page.goto("/#/terms/fi");
  await expect(page.getByRole("heading", { level: 1, name: "Käyttöehdot" })).toBeVisible();
  await expect(page.locator("article.legal")).toContainText("ei ole arvoa");
});

test("every page links to both, in both languages, and the links lead there", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Network" })).toBeVisible();
  const legal = page.getByRole("navigation", { name: "Privacy and terms" });
  await expect(legal.getByRole("link")).toHaveText([
    "Privacy notice",
    "Terms of use",
    "Tietosuojaseloste",
    "Käyttöehdot",
  ]);
  await expect(legal.getByRole("link", { name: "Käyttöehdot" })).toHaveAttribute("lang", "fi");

  await legal.getByRole("link", { name: "Privacy notice" }).click();
  await expect(page).toHaveURL(/#\/privacy$/);
  await expect(page.getByRole("heading", { level: 1, name: "Privacy notice" })).toBeFocused();
  // The language link moves to the other version, and focus to its heading.
  await page.getByRole("link", { name: "Suomeksi" }).click();
  await expect(page).toHaveURL(/#\/privacy\/fi$/);
  await expect(page.getByRole("heading", { level: 1, name: "Tietosuojaseloste" })).toBeFocused();
  await expect(page).toHaveTitle("Tietosuojaseloste · Orbit Watch");
  // The notice links to the terms in its own language.
  await page.locator("article.legal").getByRole("link", { name: "käyttöehtojen" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Käyttöehdot" })).toBeFocused();
});
