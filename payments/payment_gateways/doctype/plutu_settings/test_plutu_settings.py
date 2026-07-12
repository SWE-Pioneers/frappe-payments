# Copyright (c) 2026, SWE Pioneers and contributors
# For license information, please see license.txt

# NOTE: these are a light scaffold only — Plutu Settings is a Single doctype that talks to a
# live third-party API (https://api.plutus.ly). Real coverage (mocking make_post_request,
# asserting Integration Request state transitions across the redirect + OTP flows, and the
# on_payment_authorized side effect) needs to be exercised on a bench with the `payments` app
# installed; these tests are not runnable standalone in this fork.

import frappe
from frappe.tests.utils import FrappeTestCase

from payments.payment_gateways.doctype.plutu_settings.plutu_settings import (
	GATEWAYS,
	OTP_GATEWAYS,
	REDIRECT_GATEWAYS,
)


class TestPlutuSettings(FrappeTestCase):
	def test_gateway_maps_are_consistent(self):
		# every sub-gateway is classified as exactly one of redirect/OTP, and known to Plutu's API
		self.assertEqual(set(REDIRECT_GATEWAYS) | set(OTP_GATEWAYS), set(GATEWAYS.keys()))
		self.assertEqual(set(REDIRECT_GATEWAYS) & set(OTP_GATEWAYS), set())

	def test_validate_transaction_currency_rejects_non_lyd(self):
		settings = frappe.get_single("Plutu Settings")
		self.assertRaises(frappe.ValidationError, settings.validate_transaction_currency, "USD")
		# LYD must not raise
		settings.validate_transaction_currency("LYD")

	def test_get_payment_url_requires_reference_doc(self):
		settings = frappe.get_single("Plutu Settings")
		self.assertRaises(
			frappe.ValidationError,
			settings.get_payment_url,
			amount=10,
			currency="LYD",
		)
