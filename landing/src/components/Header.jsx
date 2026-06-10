import "./Header.css";
import { DEMO_URL } from "../constants.js";

const LINKS = [
  { href: "#how-it-works", label: "How It Works" },
  { href: "#attacks", label: "Attacks" },
  { href: "#tech", label: "Tech Stack" },
  { href: "#team", label: "Team" },
];

export function Header() {
  return (
    <header class="header">
      <div class="container header__inner">
        <a href="#top" class="header__logo">
          SentinelDS
        </a>
        <nav aria-label="Main">
          <ul class="header__nav">
            {LINKS.map((link) => (
              <li key={link.href}>
                <a href={link.href}>{link.label}</a>
              </li>
            ))}
          </ul>
        </nav>
        <a
          href={DEMO_URL}
          class="btn btn--default cyber-chamfer-sm"
          target="_blank"
          rel="noreferrer noopener"
        >
          View Demo
        </a>
      </div>
    </header>
  );
}
