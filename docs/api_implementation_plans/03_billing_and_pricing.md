# 03 — Billing & Margin Pricing

> **Phase 1 / Order 3**
> **Prerequisite**: [01_auth_and_api_keys.md](01_auth_and_api_keys.md), [02_metering_and_rate_limiting.md](02_metering_and_rate_limiting.md)
> **Related**: [08_deployment_and_infra.md](08_deployment_and_infra.md)

---

## 1. Goal

- Charge non-owner users a **margin-loaded fee** based on metered usage.
- Get to revenue with the **least code** first (managed provider), then optionally move to direct billing for higher margin.
- Keep the **owner** at $0.

---

## 2. Current State (Code-Grounded)

- No billing of any kind.
- Two cost realities to price around (from [02](02_metering_and_rate_limiting.md)):
  - **Cache-serving** endpoints: near-zero variable cost → cover fixed server cost + profit.
  - **Paid-upstream** endpoints (`/api/transcript` Tavily, `/api/filings/chat` Google GenAI): real per-call cost → must be covered per call or you lose money on heavy users.

---

## 3. Design

### 3.1 Provider Options

| Option | Key issuance / quota | Metering | **Actual payment / payout** | Notes |
|---|---|---|---|---|
| **RapidAPI** (managed marketplace) | ✅ | ✅ | ✅ (card + payout, takes a cut) | Lowest effort; also gives you a listing/marketplace. Best first launch. |
| **Zuplo** (API gateway) | ✅ | ✅ | △ (wire up Stripe) | More control than RapidAPI, still managed. |
| **AWS API Gateway + Usage Plans** | ✅ | ✅ | ❌ (Stripe or AWS Marketplace separately) | Infra-native but does **not** collect money by itself. |
| **Direct: Stripe + own code** | own | own ([02](02_metering_and_rate_limiting.md)) | ✅ (Stripe metered billing) | Most flexible/highest margin, most work. |

> **Recommendation for a solo developer**: launch on **RapidAPI** (delegate payment/customers/payout), validate demand, then move to **Stripe direct** to grow margin once volume justifies the work.

### 3.2 Pricing Model

Tie price to the credit system from [02 §3.1](02_metering_and_rate_limiting.md):

- **Cache-serving endpoints** → flat tiers with included quota (e.g. Free 1k credits/mo, Pro $X for 100k credits/mo).
- **Paid-upstream endpoints** → **usage-based / metered** so heavy LLM/Tavily use is always covered.
- **Margin formula**: `price_per_credit = (fixed_server_cost_amortized + upstream_variable_cost) × (1 + margin%)`.
  - Measure actual upstream cost per `/api/filings/chat` and `/api/transcript` call first; set credits in [02](02_metering_and_rate_limiting.md) accordingly.

### 3.3 Owner = $0

- Achieved upstream of billing: owner uses the **private path** (no gateway) per [01 §3.1-A](01_auth_and_api_keys.md), and/or `plan='owner'` is excluded from metering ([02 §3.3](02_metering_and_rate_limiting.md)) so nothing is ever reported to the billing provider.

### 3.4 Reporting Usage to the Biller (direct/Stripe path)

```
Periodically (e.g. hourly/daily) OR on each event:
  read usage_rollup (non-owner users) ─▶ report to Stripe usage records ─▶ Stripe invoices monthly
```

- For RapidAPI, the gateway meters at its edge — you mostly just set prices and (optionally) reconcile against your own `usage_events`.

---

## 4. Implementation Steps

### Track 0 — Measure upstream cost first (prerequisite for pricing)
1. [ ] Instrument the paid-upstream endpoints (`/api/filings/chat`, `/api/transcript`) to log, **per request**, the real cost driver: LLM tokens in/out (Google GenAI) and Tavily call count. Reuse the metering hook from [02](02_metering_and_rate_limiting.md).
2. [ ] Run a batch of representative requests, compute the **average $ cost per call**, and set the credit weights in [costs.py](02_metering_and_rate_limiting.md) so that `price ≥ cost × (1 + margin)`. Without this, the credit numbers in [02 §3.1](02_metering_and_rate_limiting.md) are guesses.

### Track A — Managed (RapidAPI) — do this first
1. [ ] Deploy Origin behind the provider (Origin stays private; see [08](08_deployment_and_infra.md)).
2. [ ] Define plans & per-endpoint pricing in the provider console (map to credit weights from [02](02_metering_and_rate_limiting.md)).
3. [ ] Configure the provider to forward a secret header to Origin; Origin trusts only the gateway (and your private path).
4. [ ] Keep local `usage_events` for reconciliation/analytics.
5. [ ] Verify owner private-path access bypasses the gateway entirely.

### Track B — Direct (Stripe) — later, for margin
1. [ ] Create Stripe products/prices (metered + tiered).
2. [ ] `findata/server/billing/stripe_client.py` — report usage records from `usage_rollup`.
3. [ ] Webhook handler for subscription lifecycle (created/canceled/payment_failed) → update `users.plan`.
4. [ ] Self-serve: checkout link + `GET /api/usage` (from [02](02_metering_and_rate_limiting.md)).
5. [ ] Reconciliation job: nightly compare `usage_events` vs reported records.

---

## 5. Files to Change/Create

- Edit: `findata/server/billing/plans.py` (plan→price + quota)
- New (Track B): `findata/server/billing/stripe_client.py`, `findata/server/api/api_billing.py` (checkout + webhook), reconciliation job under `findata/server/billing/`
- Track A is mostly provider-console + deployment config ([08](08_deployment_and_infra.md)); minimal code.

> **Cross-cutting from [09](09_launch_readiness.md)**: this is where the **self-serve signup (09 §3.1)** lands — if you chose a managed gateway, signup/payment/keys come for free with Track A; if direct, the Stripe console work in Track B *is* the signup implementation. Also wire the **cost guardrails (09 §3.5)** here together with [02](02_metering_and_rate_limiting.md).

---

## 6. Verification

- [ ] Non-owner exceeding free tier is charged correctly (test-mode invoice for Stripe, or provider sandbox).
- [ ] `/api/filings/chat` (expensive) costs the user more than a cache read.
- [ ] Owner: no charge, no usage reported to the biller.
- [ ] Payment failure → plan downgraded / access restricted (Track B webhook).
- [ ] Reconciliation: provider-reported usage matches local `usage_events` within tolerance.

---

## 7. Pitfalls & Mitigations

Each pitfall is **prevented by a specific step in this plan**.

| Pitfall (what goes wrong) | How this plan prevents it |
|---|---|
| Pricing cache endpoints per-call but LLM endpoints flat (backwards) | §3.2: cache endpoints = flat/quota tiers; paid-upstream = metered per call |
| Setting credits by guesswork → negative margin on `/api/filings/chat` | Track 0: measure real per-call $ cost **before** pricing, then derive credits |
| Origin exposed publicly → users bypass billing | Track A step 3 + [08 §3.1 / step 4](08_deployment_and_infra.md): Origin trusts only the gateway secret + the private path |
| Owner routes through the gateway → you pay your own margin | Track A step 5 + [01 §3.1-A](01_auth_and_api_keys.md): owner uses the private path; checked in Verification |
| Over-building Stripe before having customers | §3.1 + step order: launch on managed (Track A); do Track B only when volume justifies it |
