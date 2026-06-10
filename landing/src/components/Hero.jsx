import "./Hero.css";
import { DEMO_URL } from "../constants.js";

export function Hero() {
  return (
    <section class="hero" id="top">
      <div class="hero__mesh" aria-hidden="true" />
      <div class="container hero__layout">
        <div>
          <p class="hero__eyebrow">Google Cloud Hackathon · Dynatrace Track</p>
          <h1 class="hero__title">
            <span class="cyber-glitch text-gradient" data-text="SENTINELDS">
              SENTINELDS
            </span>
          </h1>
          <p class="hero__subtitle cursor-blink">
            AI agent security demo — detect indirect prompt injection and data poisoning
            with Dynatrace observability, then halt risky tool calls before damage lands
          </p>
          <div class="hero__actions">
            <a
              href={DEMO_URL}
              class="btn btn--glitch cyber-chamfer-sm"
              target="_blank"
              rel="noreferrer"
            >
              View Demo
            </a>
            <a href="#how-it-works" class="btn btn--outline cyber-chamfer-sm">
              Defense Loop
            </a>
          </div>
        </div>

        <aside class="card card--holo cyber-chamfer hero__hud" aria-label="System status">
          <span class="corner corner--tl" aria-hidden="true" />
          <span class="corner corner--tr" aria-hidden="true" />
          <span class="corner corner--bl" aria-hidden="true" />
          <span class="corner corner--br" aria-hidden="true" />
          <p class="hero__hud-title">// sentinel_status.log</p>
          <div class="hero__stat-row">
            <span>agents_online</span>
            <span>3/3</span>
          </div>
          <div class="hero__stat-row">
            <span>dynatrace_feed</span>
            <span>ACTIVE</span>
          </div>
          <div class="hero__stat-row">
            <span>sentinel_gate</span>
            <span>ARMED</span>
          </div>
          <div class="hero__stat-row">
            <span>last_verdict</span>
            <span>HALT</span>
          </div>
          <div class="hero__circuit" aria-hidden="true" />
        </aside>
      </div>
    </section>
  );
}
