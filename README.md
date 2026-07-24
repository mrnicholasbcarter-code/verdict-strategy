# Verdict Edge — Edge Mining Framework

> Lightweight, low-latency mathematical engine for prediction market alpha pipelines. Enables algorithmic traders and quant researchers to decouple data ingestion from execution logic, running live features against compound logical filters evaluating profitability under friction constraints. The framework strictly gates deployment to maximize Expected Value (EV).

---

## Architecture & Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           VERDICT EDGE                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌────────────┐ │
│  │  Ingestion   │───▶│  Feature     │───▶│  Filter      │───▶│  Execution │ │
│  │  (Feeds)     │    │  Engineering │    │  Pipeline    │    │  Gateway   │ │
│  └──────────────┘    └──────────────┘    └──────────────┘    └────────────┘ │
│                            │                    │                            │
│                            ▼                    ▼                            │
│                     ┌──────────────┐    ┌──────────────┐                    │
│                     │  Validators  │    │  Risk Gates  │                    │
│                     │  (Schema,    │    │  (verdict-   │                    │
│                     │   Bounds)    │    │   risk)      │                    │
│                     └──────────────┘    └──────────────┘                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Core Principles

1. **Separation of concerns** — Ingestion, feature engineering, filtering, execution are independent stages
2. **Deterministic evaluation** — Same inputs → same outputs, always
3. **Friction-aware** — Every filter accounts for fees, spread, slippage
4. **Composable** — Pluggable validators, filters, risk gates, fee models

---

## Features

| Feature | Description |
|---------|-------------|
| **Feature Pipeline** | Composable transforms: rolling stats, regime detection, microstructure |
| **Filter Pipeline** | Logical AND/OR/NOT chains with short-circuit evaluation |
| **Fee Models** | Kalshi bounded-profit, Polymarket maker-taker, custom |
| **Risk Integration** | Native `verdict-risk` gate evaluation |
| **Backtest Native** | Direct `verdict-backtest` tearsheet generation |
| **Telemetry** | OpenTelemetry spans for every stage |

---

## Quick Start

```bash
# Install
pipx install verdict-edge

# Run edge mining
verdict-edge mine --config config/alpha_pipeline.yaml --backtest
```

## Configuration

```yaml
# config/alpha_pipeline.yaml
ingestion:
  sources:
    - type: "polymarket"
      markets: ["BTC-USD", "ETH-USD"]
      ws_url: "wss://clob.polymarket.com"

features:
  - name: "spread_bps"
    transform: "bid_ask_spread_bps"
  - name: "volume_imbalance"
    transform: "orderbook_volume_imbalance"
    window: 100

filters:
  - name: "min_edge_bps"
    type: "threshold"
    field: "expected_edge_bps"
    operator: ">="
    value: 15
  - name: "liquidity_floor"
    type: "threshold"
    field: "bid_depth_usd"
    operator: ">="
    value: 50000

risk:
  verdict_risk_config: "~/.verdict/risk_config.yaml"
  max_position_usd: 10000
  max_drawdown_pct: 0.05

execution:
  gateway: "verdict_core"
  retry_policy: "exponential"
  timeout_ms: 500
```

---

## Links

- **Verdict Core**: https://github.com/verdict/verdict-core
- **Verdict Risk**: https://github.com/verdict/verdict-risk
- **Verdict Backtest**: https://github.com/verdict/verdict-backtest
- **RuVector**: https://github.com/ruvnet/ruvector
- **Ruflo**: https://github.com/ruvnet/claude-flow

---

## License

MIT — see [LICENSE](LICENSE)
