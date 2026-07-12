# Copyright (c) 2026, SWE Pioneers and contributors
# For license information, please see license.txt

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.integrations.utils import create_request_log
from frappe.model.document import Document

from payments.utils import create_payment_gateway

# TODO(bench-verify): confirm the real Moamalat hosted-checkout base URL with the
# merchant onboarding docs. The ported client (mailbox/api/gateways/moamalat.py)
# only wired a client-side LightBox script URL, not a server-redirect URL — this
# is the closest analogous hosted-checkout endpoint and MUST be verified live.
MOAMALAT_CHECKOUT_URL = "https://webapi.moamalat.net/hostedcheckout"


class MoamalatSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		moamalat_data_service_url: DF.Data | None
		moamalat_merchant_id: DF.Data
		moamalat_return_url: DF.Data | None
		moamalat_secure_key: DF.Password
		moamalat_terminal_id: DF.Data
		redirect_to: DF.Data | None
	# end: auto-generated types

	supported_currencies = ("LYD",)

	def on_update(self):
		create_payment_gateway("Moamalat")

	def validate_transaction_currency(self, currency):
		if currency not in self.supported_currencies:
			frappe.throw(
				_(
					"Please select another payment method. Moamalat does not support transactions in currency '{0}'"
				).format(currency)
			)

	def _generate_secure_hash(self, amount_smallest, merchant_reference, trx_date_time, return_url):
		"""Port of MoamalatGateway._generate_secure_hash (mailbox/api/gateways/moamalat.py)."""
		secure_key = self.get_password("moamalat_secure_key")
		raw = (
			f"{amount_smallest}{self.moamalat_merchant_id}{merchant_reference}"
			f"{return_url}{secure_key}{self.moamalat_terminal_id}{trx_date_time}"
		)
		return hashlib.sha256(raw.encode("utf-8")).hexdigest()

	def get_payment_url(self, **kwargs):
		if not kwargs.get("order_id") or not kwargs.get("amount"):
			frappe.throw(_("Missing order ID or amount"))

		integration_request = create_request_log(kwargs, service_name="Moamalat")

		amount_smallest = str(int(round(float(kwargs.get("amount")) * 1000)))
		merchant_reference = kwargs.get("order_id") or integration_request.name
		trx_date_time = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
		return_url = (
			kwargs.get("redirect_to") or self.moamalat_return_url or frappe.utils.get_url()
		)

		secure_hash = self._generate_secure_hash(
			amount_smallest, merchant_reference, trx_date_time, return_url
		)

		integration_request_dict = frappe.parse_json(integration_request.data)
		integration_request_dict.update(
			{
				"merchant_reference": merchant_reference,
				"amount_smallest": amount_smallest,
				"trx_date_time": trx_date_time,
				"return_url": return_url,
			}
		)
		integration_request.data = frappe.as_json(integration_request_dict)
		integration_request.save(ignore_permissions=True)
		frappe.db.commit()

		query_params = {
			"mid": self.moamalat_merchant_id,
			"tid": self.moamalat_terminal_id,
			"amountTrxn": amount_smallest,
			"merchantReference": merchant_reference,
			"trxDateTime": trx_date_time,
			"secureHash": secure_hash,
			"returnUrl": return_url,
		}

		return f"{MOAMALAT_CHECKOUT_URL}?{urlencode(query_params)}"


@frappe.whitelist(allow_guest=True)
def callback():
	try:
		data = frappe.request.get_json(silent=True) or frappe.request.form or frappe.request.args

		merchant_reference = data.get("MerchantReference") or data.get("merchantReference")
		if not merchant_reference:
			frappe.throw(_("Missing Merchant Reference"))

		incoming_secure_hash = data.get("SecureHash") or data.get("secureHash")
		if not incoming_secure_hash:
			frappe.throw(_("Missing Secure Hash"))

		integration_request_doc = get_integration_request(merchant_reference)
		integration_request_dict = frappe.parse_json(integration_request_doc.data)

		settings = frappe.get_single("Moamalat Settings")
		expected_secure_hash = settings._generate_secure_hash(
			integration_request_dict.get("amount_smallest"),
			merchant_reference,
			integration_request_dict.get("trx_date_time"),
			integration_request_dict.get("return_url"),
		)

		if expected_secure_hash.lower() != str(incoming_secure_hash).lower():
			integration_request_doc.status = "Failed"
			integration_request_doc.error = "Secure hash validation failed"
			integration_request_doc.save(ignore_permissions=True)
			frappe.db.commit()
			frappe.throw(_("Invalid Secure Hash"))

		status = str(data.get("Status") or data.get("status") or "").lower()
		is_payment_successful = status in ("completed", "success", "approved", "captured", "paid")

		integration_request_dict.update(
			{
				"system_reference": data.get("SystemReference"),
				"network_reference": data.get("NetworkReference"),
			}
		)
		integration_request_doc.data = frappe.as_json(integration_request_dict)

		if is_payment_successful:
			integration_request_doc.status = "Completed"
			integration_request_doc.save(ignore_permissions=True)
			frappe.db.commit()

			return handle_payment_success(integration_request_dict)
		else:
			integration_request_doc.status = "Failed"
			integration_request_doc.error = f"Payment Status: {status}"
			integration_request_doc.save(ignore_permissions=True)
			frappe.db.commit()
			frappe.log_error(frappe.get_traceback(), "Moamalat Payment not authorized")

	except Exception:
		frappe.log_error(frappe.get_traceback(), "Moamalat Callback Error")


def get_integration_request(merchant_reference):
	"""Fetch Integration Request linked to a Moamalat merchant reference."""

	integration_requests = frappe.get_all(
		"Integration Request",
		filters={
			"integration_request_service": "Moamalat",
			"data": ["like", f'%"merchant_reference": "{merchant_reference}"%'],
		},
		fields=["name", "data", "reference_doctype", "reference_docname"],
		order_by="creation desc",
		limit=1,
	)
	if not integration_requests:
		frappe.throw(_("No Integration Request found for this Merchant Reference"))

	return frappe.get_doc("Integration Request", integration_requests[0].name)


def handle_payment_success(integration_request_dict):
	"""Handle post-success payments. Mirrors paymob_settings.handle_payment_success.

	Does NOT create a Payment Entry directly — ERPNext's Payment Request creates it
	from the reference document's on_payment_authorized hook.
	"""

	redirect_to = integration_request_dict.get("redirect_to")
	reference_doctype = integration_request_dict.get("reference_doctype")
	reference_docname = integration_request_dict.get("reference_docname")

	if reference_doctype and reference_docname:
		custom_redirect_to = None
		try:
			custom_redirect_to = frappe.get_doc(reference_doctype, reference_docname).run_method(
				"on_payment_authorized", "Completed"
			)
		except Exception:
			frappe.log_error(frappe.get_traceback())

		if custom_redirect_to:
			redirect_to = custom_redirect_to

	redirect_url = f"payment-success?doctype={reference_doctype}&docname={reference_docname}"

	if redirect_to:
		redirect_url += "&" + urlencode({"redirect_to": redirect_to})

	return {"redirect_to": redirect_url, "status": "Completed"}
