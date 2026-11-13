# Accessibility review of the web application

Phase 3, step 3.8. Target: WCAG 2.2 level AA, in English
([P3-09](decisions.md#p3-09-accessibility-language-and-labels)). Reviewed on
2026-11-13 against the local stack, version 0.4.0.

## How

Every view was opened as the role that uses it and checked in three ways.
The check is the end-to-end test
[`web/e2e/a11y.spec.ts`](../web/e2e/a11y.spec.ts), which CI runs on every
pull request (criterion 10 of [P3-11](decisions.md#p3-11-phase-3-completion-criteria)).

1. **axe** (`@axe-core/playwright`) with the WCAG 2.0, 2.1 and 2.2 rules of
   levels A and AA, in light and in dark colours.
2. **The keyboard alone:**
   - Tab goes from the top of the page to its end and leaves it, so there is
     no trap.
   - Every stop is shown, with a focus indicator of at least 2 pixels.
   - The first stop is the skip link, and Enter on it takes focus to the
     page's heading.
   - A page change moves focus to the new heading
     ([D-25](decisions.md#d-25-the-web-project)).
3. **Reflow** (WCAG 1.4.10): at 320 CSS pixels wide, nothing scrolls
   sideways. Tables scroll inside their own frame.

The role tests also run axe on the states a view passes through: a filled
form, the transaction check before signing, a delivery's verification check
by check, a vote, a prepared Safe transaction, and the quality meter's
report.

## Views

| View | Address | Role | Keyboard stops |
|---|---|---|---|
| Network | `#/` | anyone | 8 |
| Open requests | `#/requests` | anyone | 8 |
| Attestations | `#/attestations` | anyone | 8 |
| Station quality meter | `#/quality` | anyone | 10 |
| Sign in | `#/sign-in` | anyone | 8 |
| Page not found | `#/nowhere` | anyone | 9 |
| Your account | `#/account` | requester | 11 |
| Your requests | `#/my-requests` | requester | 17 |
| New request | `#/new-request` | requester | 43 |
| A request | `#/requests/<id>` | its requester | 12 |
| A settled request | `#/requests/<id>` | its observer | 13 |
| Open requests | `#/requests` | station | 14 |
| Your station | `#/station` | station | 16 |
| Your observations | `#/my-observations` | station | 12 |
| Your review tasks | `#/tasks` | reviewer | 12 |
| A review task | `#/tasks/<id>` | reviewer | 14 |
| Administration | `#/admin` | administrator | 37 |

All 17 views pass all three checks, with no axe violations in either colour
scheme.

## Found and fixed

- **Date and time fields showed no focus.** In Chromium, a
  `datetime-local` field takes focus in its parts (day, month, hour), inside
  the field, so the page's `:focus-visible` outline never appeared on it. The
  whole field is now outlined while any part of it has focus. The new
  request's window and deadline and the simulator's window use these fields.

Found and fixed in earlier steps, and kept by their tests:
- a long wallet address made the sign-up page scroll sideways on a phone
  (3.2);
- the administrator view's tables are named, so that a screen reader tells
  them apart (3.7);
- the result of `tick` is a live status that stays while the page reloads
  (3.7).

## Not covered

This review is automated. Automated checks find only part of the barriers
that people meet. Not done:

- **Screen readers.** No test was made with NVDA, JAWS, VoiceOver or
  TalkBack. The pages use headings, landmarks, labelled forms, live statuses
  for results and alerts for refusals, but how they sound has not been
  heard.
- **Other browsers.** Only Chromium was tested; Firefox and Safari were not.
- **Zoom and text spacing** beyond the 320-pixel reflow check (WCAG 1.4.4,
  1.4.12).
- **People.** No one who relies on assistive technology has used the
  application yet.
- **Wallets and the Safe app.** A wallet extension's own windows, and the
  Safe app, are outside Orbit Watch.

These are open for a later phase. A public service would need at least a
screen reader test and a test with users first
([P3-10](decisions.md#p3-10-no-public-deployment-in-phase-3)).
