import "./Hero.css";
import { DEMO_URL } from "../constants.js";

export function Hero() {
  return (
    <section class="hero" id="top">
      <div class="hero__mesh" aria-hidden="true" />
      <div class="container hero__layout">
        <div>
          <p class="hero__eyebrow">Runtime Security for Agentic AI</p>
          <h1 class="hero__title">
            <span class="cyber-glitch text-gradient" data-text="SENTINELDS">
              SENTINELDS
            </span>
          </h1>
          <p class="hero__subtitle cursor-blink">
            The immune system for AI agents. Inspect every tool call, detect
            prompt injection and data poisoning in flight, and halt risky actions
            before they reach production.
          </p>
          <div class="hero__actions">
            <a
              href={DEMO_URL}
              class="btn btn--glitch cyber-chamfer-sm"
              target="_blank"
              rel="noreferrer noopener"
            >
              See It In Action
            </a>
            <a href="#how-it-works" class="btn btn--outline cyber-chamfer-sm">
              How It Works
            </a>
          </div>
        </div>

        <aside class="card card--holo cyber-chamfer hero__hud" aria-label="Platform telemetry">
          <span class="corner corner--tl" aria-hidden="true" />
          <span class="corner corner--tr" aria-hidden="true" />
          <span class="corner corner--bl" aria-hidden="true" />
          <span class="corner corner--br" aria-hidden="true" />
          <p class="hero__hud-title">// sentinel.runtime</p>
          <div class="hero__stat-row">
            <span>tool_calls_inspected</span>
            <span>1.2M+</span>
          </div>
          <div class="hero__stat-row">
            <span>threats_neutralized</span>
            <span>3,481</span>
          </div>
          <div class="hero__stat-row">
            <span>median_decision</span>
            <span>42ms</span>
          </div>
          <div class="hero__stat-row">
            <span>policy_engine</span>
            <span>ARMED</span>
          </div>
          <div class="hero__circuit" aria-hidden="true" />
        </aside>
      </div>
    </section>
  );
}
