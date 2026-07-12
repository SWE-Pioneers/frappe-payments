# Copyright (c) 2026, SWE Pioneers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

no_cache = 1

expected_keys = (
	"transaction_id",
	"integration_request",
	"reference_doctype",
	"reference_docname",
	"amount",
	"currency",
)


def get_context(context):
	context.no_cache = 1

	if not (set(expected_keys) - set(list(frappe.form_dict))):
		for key in expected_keys:
			context[key] = frappe.form_dict[key]

		context["amount"] = flt(context["amount"])
	else:
		frappe.redirect_to_message(
			_("Some information is missing"),
			_("Looks like someone sent you to an incomplete URL. Please ask them to look into it."),
		)
		frappe.local.flags.redirect_location = frappe.local.response.location
		raise frappe.Redirect
