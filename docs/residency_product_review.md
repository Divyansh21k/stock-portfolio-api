# Residency Product Review: StockPulse

## Who this should be for
- Primary persona: self-directed retail investor with 5-20 US equities, checks portfolio daily, struggles to prioritize risk signals.

## Problem statement
- Existing brokers show charts and metrics, but users still ask: "What should I do now?"
- StockPulse should prioritize risk and next actions, not just provide data.

## Startup pitch (2-3 lines)
StockPulse is a portfolio copilot for retail investors.
It converts noisy technical indicators into clear daily risk alerts, explanations, and suggested actions.
In 30 seconds, an investor can see what position needs attention first and why.

## 5-day execution plan
1. Add actionable recommendations into `/portfolio/insights` (`hold`, `trim`, `rebalance`, `review thesis`).
2. Add `next_best_action` summary card endpoint (`/portfolio/action-center`).
3. Simplify UI to one-page flow: input holdings -> insights feed -> action checklist.
4. Add tiny demo seed endpoint to preload portfolio for evaluator walkthrough.
5. Tighten API response envelope with timestamps, severity, and confidence fields.
