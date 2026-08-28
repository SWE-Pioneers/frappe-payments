# Payments

A payments app for frappe.

## Installation
1. Install [bench & frappe](https://frappeframework.com/docs/v14/user/en/installation).

2. Once setup is complete, add the payments app to your bench by running
    ```
    $ bench get-app payments
    ```
3. Install the payments app on the required site by running
    ```
    $ bench --site <sitename> install-app payments
    ```

## App Structure & Details
App has 2 modules - Payments and Payment Gateways.

Payment Module contains the Payment Gateway DocType which creates links for the payment gateways and Payment Gateways Module contain all the Payment Gateway (Razorpay, Stripe, Braintree, Paypal, PayTM) DocTypes.

App adds custom fields to Web Form for facilitating payments upon installation and removes them upon uninstallation.

All general utils are stored in [utils](payments/utils) directory. The utils are written in [utils.py](payments/utils/utils.py) and then imported into the [`__init__.py`](payments/utils/__init__.py) file for easier importing/namespacing.

[overrides](payments/overrides) directory has all the overrides for overriding standard frappe code. Currently it overrides WebForm DocType controller as well as a WebForm whitelisted method.

[templates](payments/templates) directory has all the payment gateways' custom checkout pages.

## Buyer-selectable gateways

A consuming app (LMS is the first) can let a buyer pick a payment method at checkout
instead of hard-coding a single gateway. Tick `Show in Checkout` on each `Payment Gateway`
you want to expose, then in the app:

1. Render the checkout selector from `get_enabled_payment_gateways()` — it returns the
   gateways an admin has ticked `show_in_checkout` **and** that are actually configured
   (credentials filled in), each as `{"name": ..., "label": ...}`. It is whitelisted, so a
   frappe-ui `createResource` can call `payments.utils.get_enabled_payment_gateways` directly.
2. Take the buyer's choice and pay via
   `get_payment_gateway_controller(chosen).get_payment_url(**details)`.

Enabling nothing keeps today's single-gateway behavior, so adoption is backward-compatible.

## Ongoing Work
- New API design: https://github.com/frappe/payments/pull/53
- Mollie Integration: https://github.com/frappe/payments/pull/68 (awaiting the former, but you may use the branc)

## License
MIT ([license.txt](license.txt))
