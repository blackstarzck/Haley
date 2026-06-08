---
name: Obsidian Signal
colors:
  surface: '#0c160e'
  surface-dim: '#0c160e'
  surface-bright: '#323c32'
  surface-container-lowest: '#071009'
  surface-container-low: '#141e16'
  surface-container: '#18221a'
  surface-container-high: '#222c24'
  surface-container-highest: '#2d372e'
  on-surface: '#dae6d8'
  on-surface-variant: '#b9cbb9'
  inverse-surface: '#dae6d8'
  inverse-on-surface: '#29332a'
  outline: '#849585'
  outline-variant: '#3b4b3d'
  surface-tint: '#00e479'
  primary: '#f1ffef'
  on-primary: '#003919'
  primary-container: '#00ff88'
  on-primary-container: '#007139'
  inverse-primary: '#006d37'
  secondary: '#c5c6cb'
  on-secondary: '#2e3134'
  secondary-container: '#44474b'
  on-secondary-container: '#b3b5b9'
  tertiary: '#fffaf7'
  on-tertiary: '#3d2f00'
  tertiary-container: '#ffdb79'
  on-tertiary-container: '#795f01'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#60ff99'
  primary-fixed-dim: '#00e479'
  on-primary-fixed: '#00210c'
  on-primary-fixed-variant: '#005228'
  secondary-fixed: '#e1e2e7'
  secondary-fixed-dim: '#c5c6cb'
  on-secondary-fixed: '#191c1f'
  on-secondary-fixed-variant: '#44474b'
  tertiary-fixed: '#ffe08d'
  tertiary-fixed-dim: '#e5c364'
  on-tertiary-fixed: '#241a00'
  on-tertiary-fixed-variant: '#584400'
  background: '#0c160e'
  on-background: '#dae6d8'
  surface-variant: '#2d372e'
  status-block: '#FF3B3B'
  status-warning: '#FFB800'
  status-pass: '#00FF88'
  status-neutral: '#6B7280'
  surface-card: rgba(22, 26, 30, 0.7)
  border-glass: rgba(255, 255, 255, 0.08)
  text-dim: '#94A3B8'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  data-mono-lg:
    fontFamily: JetBrains Mono
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  data-mono-md:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  data-mono-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 14px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  container-margin: 24px
  gutter: 16px
  widget-padding: 20px
  row-tight: 8px
  section-gap: 32px
---

## Brand & Style

This design system is engineered for **Obsidian Signal**, a high-precision automated trading environment. The brand personality is rooted in **vigilance, technical mastery, and structural integrity**. It moves away from the "gamified" retail trading experience toward a professional, terminal-like interface that prioritizes data density and operational safety.

The visual style is a fusion of **Modern Dark-Mode** and **Technical Glassmorphism**. It utilizes a deep charcoal foundation to minimize eye strain during long-term monitoring, punctuated by high-vibrancy "Neon Signal" accents. The interface relies on subtle frosted overlays and high-contrast status indicators to separate critical alerts from background telemetry. Every element is designed to answer the operator's primary question: *Is the system safe, and why is it making this decision?*

## Colors

The palette is optimized for a low-light "War Room" environment.

- **Primary (Neon Green):** Reserved exclusively for bullish signals, "Signal Pass" states, and successful execution. It serves as the "Go" signal.
- **Background (Midnight):** A solid, non-distracting charcoal used for the base layer to maximize the luminance of data points.
- **Status Logic:**
    - **Hard Block (Red):** Used for Kill-Switch events and critical system failures.
    - **Data Quality (Yellow):** Indicates stale data, API latency, or partial fills.
    - **Signal Pass (Neon Green):** Indicates optimal trading conditions.
    - **Neutral (Gray):** Used for inactive states, dry-run modes, and secondary telemetry.

Interactive elements use semi-transparent surface colors (`surface-card`) to create a layered glass effect, ensuring the UI feels deep and sophisticated rather than flat.

## Typography

Typography is treated as a functional tool for data parsing.

- **Inter (Sans-Serif):** Used for UI chrome, navigation, and descriptive text where readability and neutrality are paramount.
- **JetBrains Mono (Monospaced):** Used for all numerical values, price tickers, timestamps, and JSON logs. This ensures that numbers align perfectly in tables, allowing for rapid vertical scanning of price movements.
- **Status Enums:** All system states (e.g., `LIVE`, `PAPER`, `RECONCILED`) must be rendered in `label-caps` to distinguish system-generated logic from user-facing labels.

## Layout & Spacing

The design system utilizes a **Fixed Grid Dashboard** model optimized for 1440p and 4K displays, with a simplified single-column reflow for mobile monitoring.

- **Information Density:** High. Use `row-tight` (8px) for table rows and list items to maximize the volume of visible data without sacrificing touch/click targets.
- **Structure:** A persistent sidebar for navigation, a global header for "Total Equity" and "Kill-Switch" access, and a modular masonry-style grid for widgets (Charts, Order Book, Logs).
- **Safe Areas:** Maintain a `container-margin` of 24px on all edges to ensure the technical data feels contained and professional, never "bleeding" into the bezel.

## Elevation & Depth

Depth is established through **Tonal Layering and Glassmorphism** rather than traditional drop shadows.

1.  **Base (Level 0):** The midnight background (#0B0E11).
2.  **Surface (Level 1):** Widgets and cards use a semi-transparent dark fill with a subtle `border-glass` (8% white). This creates a sense of the interface floating over the system engine.
3.  **Active (Level 2):** Hover states or active modals utilize a background blur (Backdrop Filter: 12px) to visually pull the element forward.
4.  **Signal Layer:** Ticker prices and indicators utilize an outer glow (bloom) effect in their respective status color when a significant event occurs (e.g., a "Signal Pass" flash).

## Shapes

The shape language is **Technical and Precise**.

- **Soft Edges (4px - 8px):** Components use a "Soft" radius to prevent the UI from feeling overly aggressive or "brutalist," while maintaining a sharp, professional edge.
- **Status Badges:** Use a slightly higher radius (rounded-lg) to create a distinct visual profile compared to the sharp-cornered data tables.
- **Inputs:** Buttons and text fields should be consistent with the 4px base radius to reinforce a sense of structural stability.

## Components

- **Buttons:**
    - **Primary:** Solid Neon Green background with black text for high-impact actions like "Place Order."
    - **Ghost:** `border-glass` with white or dimmed text for secondary actions.
    - **Emergency:** Solid Red background with white text for the "Kill-Switch."
- **Status Badges:**
    - High-contrast, all-caps labels. `LIVE` mode should feature a subtle "pulse" animation to signify an active connection.
- **Data Tables:**
    - No vertical borders. Horizontal borders should be low-contrast (rgba 255, 255, 255, 0.05).
    - Header labels should be `label-caps` in `text-dim`.
- **Glass Cards:**
    - Every widget container must have a 1px solid border at 8% opacity and a backdrop blur to maintain legibility against potential background data viz.
- **Input Fields:**
    - Deep inset backgrounds with monospaced text to ensure currency values are perfectly legible during entry.