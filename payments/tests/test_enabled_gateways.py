import frappe
from frappe.tests.utils import FrappeTestCase

from payments.utils.utils import get_enabled_payment_gateways, is_gateway_configured


class TestEnabledGateways(FrappeTestCase):
	def test_excludes_disabled_and_unconfigured(self):
		# A gateway not shown in checkout is never returned, even if configured.
		names = {g["name"] for g in get_enabled_payment_gateways()}
		disabled = frappe.get_all(
			"Payment Gateway", filters={"show_in_checkout": 0}, pluck="name"
		)
		self.assertTrue(names.isdisjoint(set(disabled)))
		# Every returned gateway is configured.
		for g in get_enabled_payment_gateways():
			self.assertTrue(is_gateway_configured(g["name"]))
