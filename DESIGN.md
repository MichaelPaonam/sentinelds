# SentinelDS Dashboard — Terminal CLI Design Specification

This document defines the retro-brutalist **Terminal CLI** design system for the **SentinelDS SaaS Observability Dashboard**. All subsequent modifications, additions, or redesigns to the frontend interface (`src/dashboard/`) must strictly comply with these specifications to preserve the authentic **Cyber-Industrial Phosphor Monitor** aesthetic.

---

## 1. Core Philosophy & Constraints

*   **100% Pure Vanilla Web**: Built entirely with standard HTML5, CSS3, and ES6 JavaScript. No build steps, no JSX/TSX compilers, no module bundlers, and zero third-party Node.js dependencies.
*   **Local File System Portability**: The dashboard must load, render, and execute flawlessly when opened directly from the file system (e.g., via `file:///` protocols in Google Chrome/Firefox) or via an advisory local HTTP server (`python -m http.server`).
*   **Total Monospace Uniformity**: A standard monospace layout where every character, label, title, and form occupies perfect fixed-width grid alignments.
*   **Brutalist Borders**: Absolute enforcement of hard edges. **No rounded corners are permitted (`border-radius: 0px !important`).**

---

## 2. Design Token System

### A. Color Palette
The color tokens model a vintage high-contrast monochrome cathode phosphor screen:

| Token | CSS Value | Description | Usage |
| :--- | :--- | :--- | :--- |
| `--bg-dark` | `#050705` | Deep cathode pitch black | Global viewport and pane background |
| `--primary` | `#33ff00` | Bright neon green phosphor | Text, primary frames, successful states (`[ OK ]`) |
| `--secondary` | `#ffb000` | Vintage warning Amber/Orange | Warnings, indicators, active anomalies (`[ WARN ]`) |
| `--muted` | `#12380a` | Muted scanline/grid green | Pane header background, coordinate grids, inactive frames |
| `--error` | `#ff3333` | Neon alarm red | Quarantined states, blockages, halted verdicts (`[ HALT ]`) |

### B. Typography & Sizing
*   **Primary Font**: Google Fonts `VT323` loaded via `<link>` tag.
*   **Fallback Font Family**: `monospace`.
*   **Global Font Size**: `20px` to maintain optimal high-contrast legibility for compact monospace characters.
*   **Letter Spacing**: `0.5px` or `0.8px` for headers.

### C. Visual Effects & Physics
*   **Phosphor Halo Glow**: Text elements use a subtle shadow persistence:
    ```css
    text-shadow: 0 0 6px rgba(51, 255, 0, 0.55);
    ```
*   **Step Transitions**: Hover and state transitions must avoid smoothed curves and utilize a stepped sequence:
    ```css
    transition: all 0.1s steps(3);
    ```

---

## 3. Screen Overlay Effects (CRT Cathode Monitors)

To mimic vintage raster scan displays, the main HTML document must overlay two pointer-events-none elements directly wrapping the viewport:

1.  **Scanline Grate Overlay (`.scanlines`)**: Creates horizontal raster lines via a fine gradient overlay repeating every 3px:
    ```css
    background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.2) 50%);
    background-size: 100% 3px;
    ```
2.  **Cathode Flickering Overlay (`.crt-overlay`)**: Renders a subtle radial gradient vignette simulating physical glass monitor curvature, accompanied by a rapid micro-flicker keyframe animation mimicking phosphor raster persistence:
    ```css
    background: radial-gradient(circle, rgba(51, 255, 0, 0.03) 0%, rgba(0, 0, 0, 0.3) 100%);
    animation: monitor-flicker 0.15s infinite;
    ```

---

## 4. UI Layout & Component Guidelines

The interface layout is a standard split-pane Tmux-style terminal grid containing four discrete panels.

```
+---------------------------------------------------------------------------------+
|                                 TERMINAL HEADER                                 |
|  [ASCII Logo] [root@sentinelds:~# run...]                                       |
|  Controls: [ DEMO DATA ]  [ F1: Scenario A1 ] [ F2: Scenario A2 ] [ F5: PLAY ]  |
+-------------------------------------+-------------------------------------------+
| PANEL 1: SYSTEM SERVICES STATUS     | PANEL 2: DYNATRACE SYSTEM DIAGNOSTICS     |
| [ OK ] RESEARCH_AGENT   PID: 1042   | >>> [SEVERE] ANOMALOUS AGENT EGRESS...    |
| [ERR ] MODELLING_AGENT  PID: 1044   | >>> [SEVERE] PROMPT INJECTION CANDIDATE   |
+-------------------------------------+-------------------------------------------+
| PANEL 3: SENTINEL PRE-FLIGHT DECISION MATRIX                                    |
| | TIME     | PROCESS       | INTERCEPTED CALL          | RULE       | VERDICT | |
| | 03:04:12 | RESEARCH_AGENT| web_fetch('attacker...')  | Egress Host| [HALT]  | |
+---------------------------------------------------------------------------------+
| PANEL 4: MLSECOPS DRIFT RADAR (Oscilloscope display)                            |
| (Vector SVG, safety limit lines, anomaly shading overlays)                      |
+---------------------------------------------------------------------------------+
```

### A. Logo and Prompts
*   The header utilizes a static monospace ASCII art logo representing `SENTINELDS`.
*   Interactive shell prompts must feature a flashing terminal block cursor (`█`) driven by keyframe steps.

### B. Button Controls
*   Styled checkboxes, toggles, or circular switches are strictly prohibited.
*   Interactive options must be styled as bracket-bordered text blocks (e.g., `[ F5: PLAY SIMULATION ]`).
*   Hovering over any bracket button must invert its background and text instantly (`background: var(--primary)` and `color: var(--bg-dark)`), removing the text shadow.

### C. Workspace Overview (System Daemon Tables)
*   Agents must be styled as active background server systemd processes inside a process-table row layout.
*   Statuses are bounded by brackets (`[ OK ]` for healthy, `[WRN]` for compromised, `[ERR]` for quarantined/halted).

### D. Problem Feed (Syslog Blocks)
*   Active problems must resemble direct raw kernel panics or chronological stdout syslog logs (`syslog-card`).
*   Severe logs feature a bold red left-border accent (`border-left: 2px solid var(--error)`) and a subtle red backlight background.

### E. Decision Log (Tabular ASCII Formatter)
*   To prevent text wrapping from breaking column alignments inside `<pre>` blocks, the JS engine must implement a string-padding helper function `pad(str, length)` to mathematically pad each cell with trailing whitespace character boundaries.
*   Rows must be aligned to the headers:
    ```text
    | TIME     | SOURCE PROCESS  | INTERCEPTED SYSTEM CALL   | SECURITY RULE       | VERDICT |
    ```

### F. Metrics Scope Chart (Cathode Oscilloscope Plot)
*   Renderings must utilize responsive SVG vectors instead of Canvas engines to ensure clean scaling.
*   Grid lines must resemble pixelated green grids (`stroke-dasharray: 2 4`).
*   Chart plots must represent sharp retro oscilloscope beams (`stroke-linejoin: miter; stroke-linecap: square`) and utilize solid vector lines to avoid curves.
*   Include a warning limit threshold horizontal line (`stroke-dasharray: 6 3`) and alert highlights using a faint, low-opacity alarm red block overlay.

---

## 5. Coding Principles & Guidelines for Changes

1.  **Do Not Import Frameworks**: Do not inject React, Vue, TailwindCSS, or any compiled CSS/JS pre-processors.
2.  **No Rounded Corners**: Do not write `border-radius` with positive values. Ensure all custom cards and tables enforce `0px`.
3.  **Color Integrity**: Only use the pre-defined CSS variables in `styles.css`. Ad-hoc color selections (like raw `#f00` or `#00f`) are forbidden.
4.  **Preserve Keyboard Shortcuts**: Button text should mention mapping functions (e.g., `[ F5: PLAY SIMULATION ]`, `[ F1: Scenario A1 ]`) matching standard physical terminal conventions.
