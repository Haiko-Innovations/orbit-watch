/** The Orbit Watch mark, in the theme's colours (decorative: the name stands next to it). */
export function Logo() {
  return (
    <svg className="logo" viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">
      <ellipse
        cx="16"
        cy="16"
        rx="13"
        ry="6"
        fill="none"
        strokeWidth="2"
        transform="rotate(-20 16 16)"
      />
      <circle className="logo-body" cx="16" cy="16" r="4" />
      <circle className="logo-satellite" cx="27" cy="11" r="2.5" />
    </svg>
  );
}
