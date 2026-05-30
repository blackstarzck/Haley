---
version: alpha
name: Haley UFS-R1 Visual Direction
description: Visual design direction for a future Upbit spot auto-trading interface. This document defines style tokens and guardrails only; it does not define final screens, layout, or feature scope.
colors:
  background: "#080B0A"
  background-glow: "#00E676"
  app-shell: "#0D0F0E"
  surface: "#101412"
  surface-raised: "#171C19"
  surface-muted: "#1F2521"
  surface-deep: "#090B0A"
  primary: "#00E676"
  primary-dim: "#00A85A"
  primary-soft: "#063C24"
  success: "#18D47B"
  warning: "#F5A524"
  danger: "#FF4D6D"
  bearish: "#FF4D6D"
  bullish: "#00D67A"
  text-primary: "#F2F7F4"
  text-secondary: "#9BA8A1"
  text-muted: "#64706A"
  border: "#26302A"
  border-soft: "#1A211D"
  focus: "#49FF9A"
  overlay: "#050706"
typography:
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: 0
  headline-md:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: 0
  section-title:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: 0
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: 0
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: 0
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: 0
  data-md:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1.35
    letterSpacing: 0
  data-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: 0
spacing:
  xxs: 2px
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
  panel-gap: 12px
  page-padding: 20px
  desktop-reference-width: 1600px
  desktop-reference-height: 1200px
rounded:
  none: 0px
  sm: 4px
  md: 8px
  lg: 10px
  xl: 12px
  full: 9999px
components:
  app-shell:
    backgroundColor: "{colors.app-shell}"
    textColor: "{colors.text-primary}"
    borderColor: "{colors.border-soft}"
    rounded: "{rounded.none}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.background}"
    typography: "{typography.label-md}"
    rounded: "{rounded.md}"
    height: 40px
    padding: 16px
  button-secondary:
    backgroundColor: "{colors.surface-muted}"
    textColor: "{colors.text-primary}"
    typography: "{typography.label-md}"
    rounded: "{rounded.md}"
    height: 36px
    padding: 14px
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.text-primary}"
    typography: "{typography.label-md}"
    rounded: "{rounded.md}"
    height: 40px
    padding: 16px
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-primary}"
    borderColor: "{colors.border}"
    rounded: "{rounded.md}"
    padding: 16px
  input:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.text-primary}"
    borderColor: "{colors.border}"
    rounded: "{rounded.md}"
    height: 38px
    padding: 12px
  segmented-control:
    backgroundColor: "{colors.surface-muted}"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.full}"
    height: 30px
  status-success:
    backgroundColor: "{colors.success}"
    textColor: "{colors.background}"
    rounded: "{rounded.full}"
  status-warning:
    backgroundColor: "{colors.warning}"
    textColor: "{colors.background}"
    rounded: "{rounded.full}"
  status-danger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.full}"
  table-row:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-secondary}"
    borderColor: "{colors.border}"
---

# Design System

## Overview

This document defines the visual direction for a future Haley UFS-R1 user interface. It is intentionally limited to design tokens, visual style, component guardrails, and image-derived aesthetic observations.

It does **not** define the final product screens, navigation structure, dashboard layout, page names, feature set, or user flows. Those decisions must come from a separate product/feature specification.

The attached images are treated as visual mood references only. They communicate a dark crypto terminal look: high-density information, black-green atmosphere, compact panels, thin borders, neon green active states, red loss/risk states, small typography, and chart/table-heavy surfaces. They must not be copied as exact screen architecture.

The product context remains UFS-R1: an Upbit spot auto-trading system. Future UI work should therefore avoid futures-specific semantics unless a later requirements document explicitly adds them.

## Colors

The palette is a black-green trading terminal system. Most surfaces are near-black. Green is the active/safe/action color. Red is loss, danger, blocked, or unresolved risk.

- **Background (`#080B0A`)**: full browser canvas.
- **Background Glow (`#00E676`)**: optional ambient glow inspired by the reference images. Use only outside or behind the main app shell, not as a decorative blob inside working panels.
- **App Shell (`#0D0F0E`)**: the main application container if a shell-style layout is chosen later.
- **Surface (`#101412`)**: primary panels, tables, chart containers.
- **Surface Raised (`#171C19`)**: input fields, selected rows, nested cards.
- **Surface Muted (`#1F2521`)**: inactive tabs, secondary control rails.
- **Surface Deep (`#090B0A`)**: chart plot backgrounds and dense table interiors.
- **Primary (`#00E676`)**: active navigation, safe primary action, selected segment, healthy connection.
- **Primary Dim (`#00A85A`)**: hover states and subtle green text.
- **Primary Soft (`#063C24`)**: green-tinted fills behind active rows or status areas.
- **Success (`#18D47B`)**: recovered, stable, protected, positive status.
- **Warning (`#F5A524`)**: cooldown, stale, pending review, degraded but not stopped.
- **Danger / Bearish (`#FF4D6D`)**: loss, blocked order, unknown order, cancel failure, kill switch confirmation.
- **Bullish (`#00D67A`)**: bullish candle and positive PnL.
- **Text Primary (`#F2F7F4`)**: core text.
- **Text Secondary (`#9BA8A1`)**: labels and secondary values.
- **Text Muted (`#64706A`)**: helper text, disabled states, timestamps.
- **Border (`#26302A`)**: panel and row separators.

Use color and text together. A red or green state must also have a readable label.

## Typography

Use **Inter** for interface text and **JetBrains Mono** for prices, balances, timestamps, order IDs, PnL, state-machine values, and table numbers.

- **Page titles**: Inter 18-24px, 700.
- **Panel titles**: Inter 14px, 700.
- **Body**: Inter 13-14px.
- **Micro labels**: Inter 11-12px, muted.
- **Data values**: JetBrains Mono 12-13px.
- **Large account totals**: Inter 24-28px, 700, with tabular number styling if available.

Avoid futuristic display fonts, excessive uppercase, heavy glow text, and crypto-gaming type. The tone should be operational and professional.

## Layout

No final layout is defined yet.

Until a product/feature specification exists, use only these layout principles:

- Prefer dense operational dashboards over marketing pages.
- Prefer compact panels, tables, charts, status strips, and filter bars over large promotional cards.
- Keep spacing tight and systematic: 4px, 8px, 12px, 16px, 24px, 32px.
- Preserve stable dimensions for tables, charts, status chips, and controls so data updates do not shift layout.
- On desktop, the visual density may resemble a trading terminal.
- On mobile, prioritize critical status and action visibility rather than trying to reproduce a desktop trading terminal.

Do not infer final page names, grid columns, sidebars, navigation tabs, or panel placement from the attached images. They are not functional wireframes for this project.

## Elevation & Depth

Depth is created through tonal layering, borders, and subtle ambient light.

- Use 1px borders and tonal contrast before shadows.
- Use darker plot/table interiors for dense data areas.
- Use selected row fills sparingly.
- Use green ambient background treatment only as a broad brand atmosphere, not as in-panel decoration.
- Dialogs may use a darker overlay and a modest shadow.

Avoid glossy 3D effects, large blur blobs inside the product UI, and decorative card stacks.

## Shapes

The shape language is compact and engineered.

- Panels: 8px radius.
- Nested cards and inputs: 8px radius.
- Small row controls: 4px radius.
- Pills, segmented controls, and status chips: full radius.
- Do not use very large rounded cards.
- Do not mix sharp panels with playful pill cards except for controls where a pill shape clearly improves scanability.

## Components

These component rules describe visual treatment only. They do not imply that all listed components must exist in the product.

- **Buttons**: 36-40px tall. Primary buttons use green fill and dark text. Secondary buttons use dark fill with border. Dangerous actions use red and confirmation.
- **Dangerous Actions**: never green. Use danger color, explicit copy, and confirmation.
- **Inputs and Selects**: dark raised surface, 1px border, visible label, focus outline in `focus`. Numeric inputs use JetBrains Mono and right alignment where appropriate.
- **Segmented Controls**: use for filters and compact mode choices if required. Active segment may be a green pill when the state is safe or neutral.
- **Panels**: compact, bordered, low-shadow. Each panel needs a short title, optional right-side control, and stable dimensions.
- **Tables**: preferred for logs, positions, orders, fills, checks, and other dense operational data.
- **Status Chips**: include both color and readable label. Examples may include `DRY_RUN`, `RECOVERY_ONLY`, `KILL_SWITCHED`, `UNKNOWN`, `CANCEL_FAILED`, `PROTECTED` if the future feature spec uses these states.
- **Charts**: if OHLC data is displayed, use candlestick charts. Bullish candles are `#00D67A`; bearish candles are `#FF4D6D`; volume uses the same direction colors at about 40% opacity. Provide tooltip or table access to OHLC values.
- **Audit/Event Lists**: if events are displayed, use append-only visual language and chronological order.
- **Modals**: use only for destructive or high-risk actions.
- **Icons**: use a consistent SVG icon set such as Lucide. Do not use emoji icons in production UI.

## Do's and Don'ts

- Do use the attached images as style references, not screen blueprints.
- Do keep the visual tone dark, compact, data-heavy, and professional.
- Do use green sparingly for healthy status, active safe controls, and primary non-danger actions.
- Do use red for loss, blocked state, unresolved risk, cancel failure, and destructive confirmation.
- Do pair every risk color with text.
- Do keep charts, tables, and panels aligned to stable dimensions when those elements are specified by future requirements.
- Do provide visible focus states and keyboard-accessible controls.
- Don't invent screens, page names, or functional panels from the reference images.
- Don't copy futures-specific concepts such as leverage, margin, short entries, liquidation price, or perpetual contracts into the spot auto-trading UI.
- Don't copy wallet card/payment transfer features unless a future product spec adds account funding workflows.
- Don't make signal score look like a guaranteed trading recommendation.
- Don't hide hard block reasons behind generic warnings.
- Don't use large glowing backgrounds inside the app shell.
- Don't use decorative orbs, marketing hero sections, or oversized editorial layouts.
- Don't use color alone to communicate whether trading is allowed or blocked.
- Don't use more than two font families.

## Product-Specific Screens

Final product screens are **not specified yet**.

This section intentionally does not define concrete pages, layout regions, navigation structure, or feature panels. A future product/feature specification must first answer:

- Who is the primary user of the UI?
- Which tasks must the UI support?
- Which data objects must be visible?
- Which actions are allowed from the UI?
- Which actions are read-only or require confirmation?
- Which states are critical enough to appear above the fold?
- Which screens are needed for P0, P1, and later releases?

Until those answers exist, AI agents should use this `DESIGN.md` only to guide visual style, token use, component treatment, accessibility, and anti-patterns.

## Implementation Fidelity Checklist

This checklist verifies style fidelity only, not feature completeness.

- The UI uses a dark, high-density fintech/trading-terminal visual language.
- Green is used for safe, active, or healthy states.
- Red is used for loss, danger, blocked, or destructive states.
- Dense data areas use compact tables, charts, rows, or status strips.
- Panels use dark surfaces, thin borders, and minimal shadow.
- Typography uses Inter for interface text and JetBrains Mono for numeric/data values.
- No UI contains leverage, margin, short entry, liquidation, or perpetual contract behavior unless a later product spec explicitly adds it.
- No UI contains payment card or real transfer behavior unless a later product spec explicitly adds it.
- No screen structure is copied directly from the reference images without a separate feature specification.
