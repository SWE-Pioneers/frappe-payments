# Libyan Payment Gateways — bench-test checklist

Native frappe-payments controllers for **Plutu / LyPay / Moamalat** (added on `version-16`), plus
the `mailbox` billing switch. This code is implemented but **not yet exercised on a bench** — verify
the following on a real site *before* removing the legacy mailbox handler.

## 0. Install + migrate
- Site has this `payments` app installed.
- `bench --site <site> migrate` — creates `Plutu Settings`, `LyPay Settings`, `Moamalat Settings`
  (Single doctypes) + the `/plutu-otp` and `/lypay-confirm` portal pages.
- Open each `* Settings` once and Save → confirm `on_update` created a `Payment Gateway` row named
  `Plutu` / `LyPay` / `Moamalat`.

## 1. Credentials
- Fill each Settings doctype with sandbox credentials (fields ported from mailbox `Payment Settings`).
- Create a `Payment Gateway Account` for each (gateway, LYD) with a receivable/debit account.

## 2. Per-gateway flow
- **Moamalat (redirect + notification):** Payment Request → `get_payment_url` → hosted checkout →
  notification → `callback()` recomputes SecureHash → Integration Request `Completed` →
  `on_payment_authorized`. ⚠ confirm the real checkout base URL + the actual notification field
  names/transport (query vs form vs JSON).
- **Plutu redirect subs (Local Bank Cards / MPGS / T-Lync):** `get_payment_url` returns Plutu
  `redirect_url` → pay → return callback → `on_payment_authorized`.
- **Plutu OTP subs (Sadad / Adfali):** `get_payment_url` returns `/plutu-otp?…` → enter OTP →
  `plutu_confirm_otp` → Plutu `/confirm` → `on_payment_authorized`. ⚠ confirm the redirect callback
  param names + the `/confirm` success field (`TODO(bench)` markers in `plutu_settings.py`).
- **LyPay (multi-step):** `get_payment_url` → `/lypay-confirm` → `confirm_payment` →
  `confirm_transfer` → `on_payment_authorized`; also test `get_status` polling + `refund_payment`
  (login-only).

## 3. Reconciliation
- After each success, confirm ERPNext's Payment Request created a **submitted Payment Entry** and the
  Sales Invoice `outstanding_amount` dropped (this replaces mailbox's bespoke Payment Entry code).

## 4. mailbox switch
- On `Payment Settings`, tick **`use_native_payment_request`**.
- Trigger billing (`billing._pay_url` / `create_checkout_session`) → confirm it routes through
  `mailbox.api.payment_request.native_checkout`, with legacy fallback on error.
- `bench --site <site> run-tests --module mailbox.tests.test_payment_request` and
  `… --module payments`.

## 5. Cut-over (only after 1–4 pass)
- Delete the legacy code listed in the `# MIGRATION — cut-over:` block at the top of
  `mailbox/api/payment_gateway.py` (PaymentGatewayHandler, GATEWAY_REGISTRY, `api/gateways/*`, the
  Libyan endpoints, the webhook registry branch) and make `use_native_payment_request` the only path.
