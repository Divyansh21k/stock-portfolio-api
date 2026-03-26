# StockPulse UI/UX Restructure Review (3–5 Day Plan)

## Executive Verdict (Direct)
The current UI optimizes for visual drama over task completion. The dashboard feels like a trading terminal demo, but portfolio users need **parallel visibility + fast decisions**. Today, key workflows (alerts + risk + decomposition) are serialized and cramped, causing context loss.

If this ships unchanged, users will bounce after the “wow” moment.

---

## 1) Layout Structure (Wireframe-Level)

## Global App Shell
- **Left rail (fixed, narrow):** Terminal, Portfolio, Holdings, Intel.
- **Top utility bar (fixed):** ticker search, market status, quick date range.
- **Main content (responsive CSS grid):** one layout system for every page.

### Grid Rules (all pages)
- Desktop (`>=1280px`): `grid-cols-12`, consistent `gap-4`.
- Tablet (`768-1279px`): `grid-cols-8`.
- Mobile (`<768px`): `grid-cols-1` stacked.
- Use `minmax(0, 1fr)` and container `overflow-hidden` to prevent overlap.

### Intel Page Wireframe
- **Row 1:** sticky section header + refresh + filter chips.
- **Row 2:** split workspace (never overlapping):
  - Left (`col-span-8`): tabbed content area.
  - Right (`col-span-4`): sticky “Live Alerts” panel.
- **Left tabs:** `Risk Profile | Decomposition | Stress Test`.
- **Right panel:** scrollable alerts list with severity counts + “show high only”.

Result: users can keep alerts visible while switching analytical views.

### Landing Page Wireframe
- **Top row:** compact KPI strip (Total Value, Day P/L, Volatility, Risk Score).
- **Middle row:** chart card (`col-span-8`) + “Action Center” (`col-span-4`).
- **Chart card default height:** `320px` (not full-screen).
- **Expand toggle:** opens modal or full-width panel when needed.

---

## 2) Critical Intel Page Fix (No More Hiding/Overwriting)

## What’s wrong now
- Risk, alerts, decomposition, and stress tools are all vertically stacked.
- Long cards push critical items out of view.
- Users lose alert context while exploring other modules.

## Recommended pattern (fastest/high-impact)
Use **Split + Tabs**:
1. Persistent right alerts panel.
2. Left tab content for risk/decomposition/stress.
3. Optional accordion inside each tab for details.

## Why this wins in 3–5 days
- Minimal backend changes.
- Mostly structural UI refactor.
- Removes overlap bug class by design.

### React sketch
```tsx
const [intelTab, setIntelTab] = useState<'risk'|'decomp'|'stress'>('risk');

<div className="grid grid-cols-12 gap-4 h-full min-h-0">
  <section className="col-span-12 xl:col-span-8 min-h-0 flex flex-col">
    <IntelTabs value={intelTab} onChange={setIntelTab} />
    <div className="mt-3 flex-1 min-h-0 overflow-auto">
      {intelTab === 'risk' && <RiskProfile />}
      {intelTab === 'decomp' && <RiskDecomposition />}
      {intelTab === 'stress' && <StressTest />}
    </div>
  </section>

  <aside className="col-span-12 xl:col-span-4 min-h-0">
    <LiveAlertsPanel className="h-full overflow-auto sticky top-2" />
  </aside>
</div>
```

### Streamlit sketch
```python
intel_tab = st.segmented_control("Intel View", ["Risk", "Decomposition", "Stress"], key="intel_tab")
left, right = st.columns([2, 1], gap="medium")

with right:
    st.subheader("Live Alerts")
    render_alerts(st.session_state.get("alerts", []))

with left:
    if intel_tab == "Risk":
        render_risk_profile()
    elif intel_tab == "Decomposition":
        render_decomposition()
    else:
        render_stress_test()
```

---

## 3) Landing Chart Improvement (Useful > Cinematic)

## Fixes
- Reduce chart default height to **280–340px**.
- Put top summary metrics beside/above chart.
- Add `Expand chart` button.
- Keep performance trend legible with fewer gridlines and clearer axis labels.

## UI behavior
- Default = decision mode (KPIs + compact chart + actions).
- Expanded = analysis mode (larger chart + indicators).

### Quick implementation rules
- Remove decorative overlays that reduce contrast.
- Keep one primary series + optional benchmark toggle.
- Limit default range to `1M`; quick switch to `1W/3M/1Y`.

---

## 4) Interactivity Upgrades (Must-Have)

## Minimum viable interactivity (ship in 3–5 days)
1. Hover tooltips with price, % change, volume.
2. Brush/time-range selector.
3. Ticker filter/search chips.
4. Toggle benchmark overlay (SPY).

## Library guidance
- You already use Chart.js; fastest path is staying with Chart.js + plugins:
  - `chartjs-plugin-zoom` (pan/zoom)
  - built-in tooltip customization
- If you need richer linked interactions later: migrate Intel analytics charts to Plotly.

### Chart.js config snippet
```js
plugins: {
  tooltip: { mode: 'index', intersect: false },
  legend: { display: true },
  zoom: {
    zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' },
    pan: { enabled: true, mode: 'x' }
  }
},
interaction: { mode: 'nearest', axis: 'x', intersect: false }
```

---

## 5) State Management / Behavior Hardening

## Current likely issue
Single global state mutations trigger unrelated re-renders and panel resets. That is why components appear to “fight” each other.

## Fix strategy
- Separate state domains:
  - `uiState`: active page/tab, panel open/closed, chart expanded.
  - `portfolioState`: holdings, P/L, metrics.
  - `intelState`: alerts, risk summary, decomposition, stress results.
- Preserve each panel’s local state when switching tabs (don’t unmount heavy components if avoidable).
- Debounce expensive requests; cache by ticker + timeframe.

### React pattern
- Use Zustand or React Context + reducers for `uiState` and `intelState`.
- Use React Query/SWR for server data; avoid manual fetch race conditions.

### Streamlit pattern
- Store each module in separate `st.session_state` keys.
- Guard reruns with `st.form` submit boundaries and memoized data loaders.

---

## 6) Design Simplification (Remove “AI-generated” Look)

## Keep
- dark theme, strong typography, concise metrics.

## Remove or tone down
- excessive gradients/glows,
- too many tiny uppercase labels,
- dense decorative borders,
- high animation frequency.

## Design system constraints (practical)
- Max 1 accent color + 1 semantic warning color.
- 8px spacing scale.
- Body text minimum 13–14px equivalent.
- One card style, one button style, one chart style per section.

---

## 7) Specific Fixes Mapped to Your 5 Problems

1. **“Impressive but not practical”**
   - Convert full-page hero visuals to compact decision cards.
   - Prioritize KPI → Alert → Action flow.

2. **“Intel page not smooth / overlap”**
   - Split layout with persistent alerts side panel + tabbed main workspace.
   - Add min-height/overflow boundaries to every card container.

3. **“Landing chart too large”**
   - Default chart 320px height + expand toggle.
   - Add summary metrics alongside chart.

4. **“Limited interactivity”**
   - Tooltip + zoom + range selector + ticker filters in first pass.

5. **“Layout fails with multiple active components”**
   - Responsive grid + explicit state domains.
   - Keep panel state isolated; avoid shared mutation collisions.

---

## 8) 3–5 Day Delivery Plan (No Full Redesign)

### Day 1
- Refactor page containers to unified responsive grid.
- Add strict overflow/min-height rules.

### Day 2
- Intel split-screen + tabs + persistent alerts panel.
- Keep existing cards; only restructure and restyle.

### Day 3
- Landing compact chart + KPI row + expand toggle.
- Remove non-essential decorative visual effects.

### Day 4
- Add chart interactions: tooltip, range, zoom, ticker filters.
- Add benchmark toggle.

### Day 5
- State cleanup (segmented stores/session state), regression pass, UX polish.

---

## Final Product Standard (What “good” looks like)
A user should be able to do this in under 20 seconds:
1. Open dashboard.
2. See risk level + top alert.
3. Switch Intel tab without losing alert context.
4. Check compact trend chart and take next action.

If any step requires scrolling through stacked cards or hunting hidden panels, the UI is still failing.
