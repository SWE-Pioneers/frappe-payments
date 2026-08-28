# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE
import frappe
from frappe.tests.utils import FrappeTestCase


class TestPaymentGateway(FrappeTestCase):
	def test_show_in_checkout_field_exists_and_defaults_off(self):
		meta = frappe.get_meta("Payment Gateway")
		df = meta.get_field("show_in_checkout")
		self.assertIsNotNone(df, "show_in_checkout field must exist")
		self.assertEqual(df.fieldtype, "Check")
		self.assertEqual(int(df.default or 0), 0)
