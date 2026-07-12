# Copyright (c) 2026, SWE Pioneers and contributors
# For license information, please see license.txt

from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.integrations.utils import create_request_log, make_post_request
from frappe.model.document import Document
from frappe.utils import get_url

from payments.utils import create_payment_gateway

BASE_URL = "https://api.plutus.ly/api/v1/transaction/"

GATEWAYS = {
	"Sadad": "sadadapi",
	"Adfali": "edfali",
	"Local Bank Cards": "localbankcards",
	"MPGS": "mpgs",
	"T-Lync": "tlync",
}

# Sub-gateways where Plutu itself hosts the checkout page and redirects the payer
# back to us (return_url/cancel_url) once done.
REDIRECT_GATEWAYS = ("Local Bank Cards", "MPGS", "T-Lync")

# Sub-gateways that use the verify -> OTP -> confirm flow instead of a redirect.
OTP_GATEWAYS = ("Sadad", "Adfali")


class PlutuSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		plutu_access_token: DF.Password
		plutu_api_key: DF.Password
		plutu_gateway: DF.Literal["Sadad", "Adfali", "Local Bank Cards", "MPGS", "T-Lync"]
		plutu_sadad_mobile: DF.Data | None
	# end: auto-generated types

	supported_currencies = ("LYD",)

	def on_update(self):
		create_payment_gateway("Plutu")

	def validate_transaction_currency(self, currency):
		if currency not in self.supported_currencies:
			frappe.throw(
				_("Please select another payment method. Plutu does not support transactions in currency '{0}'").format(
					currency
				)
			)

	def _headers(self):
		return {
			"Authorization": f"Bearer {self.get_password('plutu_access_token', raise_exception=False) or ''}",
			"X-API-KEY": self.get_password("plutu_api_key", raise_exception=False) or "",
			"Content-Type": "application/json",
			"Accept": "application/json",
		}

	def _gateway_path(self, sub_gateway=None):
		sub_gateway = sub_gateway or self.plutu_gateway
		path = GATEWAYS.get(sub_gateway)
		if not path:
			frappe.throw(_("Unsupported Plutu gateway: {0}").format(sub_gateway))
		return path

	def get_payment_url(self, **kwargs):
		sub_gateway = self.plutu_gateway or "Sadad"
		amount = kwargs.get("amount")
		currency = kwargs.get("currency") or "LYD"
		reference_doctype = kwargs.get("reference_doctype")
		reference_docname = kwargs.get("reference_docname")

		if not amount or not reference_doctype or not reference_docname:
			frappe.throw(_("Missing amount or reference document for Plutu payment"))

		self.validate_transaction_currency(currency)

		integration_request = create_request_log(kwargs, service_name="Plutu")

		try:
			if sub_gateway in REDIRECT_GATEWAYS:
				return self._get_redirect_url(sub_gateway, amount, currency, kwargs, integration_request)
			elif sub_gateway in OTP_GATEWAYS:
				return self._get_otp_url(sub_gateway, amount, currency, kwargs, integration_request)
			else:
				frappe.throw(_("Unsupported Plutu gateway: {0}").format(sub_gateway))
		except Exception:
			integration_request.db_set("status", "Failed", update_modified=False)
			frappe.log_error(frappe.get_traceback(), "Plutu Payment URL Error")
			frappe.throw(_("Could not generate Plutu payment URL"))

	def _get_redirect_url(self, sub_gateway, amount, currency, kwargs, integration_request):
		"""Local Bank Cards / MPGS / T-Lync: Plutu hosts the checkout, we get a redirect_url back."""
		gateway_path = self._gateway_path(sub_gateway)
		amount_str = str(int(round(float(amount) * 1000)))

		payload = {
			"amount": amount_str,
			"currency": currency.lower(),
			"return_url": get_url(
				"/api/method/payments.payment_gateways.doctype.plutu_settings.plutu_settings.callback"
			),
			"cancel_url": kwargs.get("cancel_url") or get_url("/payment-failed"),
			"reference_doctype": kwargs.get("reference_doctype"),
			"reference_name": kwargs.get("reference_docname"),
		}
		if sub_gateway == "T-Lync":
			payload["mobile_no"] = kwargs.get("mobile_no") or self.plutu_sadad_mobile or ""

		response = make_post_request(url=BASE_URL + gateway_path + "/confirm", json=payload, headers=self._headers())

		redirect_url = response.get("redirect_url") if response else None
		transaction_id = response.get("transaction_id") if response else None

		if not redirect_url:
			frappe.throw(_("Plutu did not return a redirect URL"))

		self._update_integration_request(
			integration_request,
			transaction_id=transaction_id,
			reference_doctype=kwargs.get("reference_doctype"),
			reference_docname=kwargs.get("reference_docname"),
			sub_gateway=sub_gateway,
			amount=amount,
			currency=currency,
		)

		return redirect_url

	def _get_otp_url(self, sub_gateway, amount, currency, kwargs, integration_request):
		"""Sadad / Adfali: verify() sends an OTP, payer confirms it on the plutu-otp portal page."""
		gateway_path = self._gateway_path(sub_gateway)
		amount_str = str(int(round(float(amount) * 1000)))
		mobile_no = kwargs.get("mobile_no") or self.plutu_sadad_mobile or ""

		if not mobile_no:
			frappe.throw(_("A mobile number is required for {0} payments").format(sub_gateway))

		response = make_post_request(
			url=BASE_URL + gateway_path + "/verify",
			json={"amount": amount_str, "mobile_no": mobile_no},
			headers=self._headers(),
		)

		transaction_id = response.get("transaction_id") if response else None
		if not transaction_id:
			frappe.throw(_("Plutu did not return a transaction for OTP verification"))

		self._update_integration_request(
			integration_request,
			transaction_id=transaction_id,
			reference_doctype=kwargs.get("reference_doctype"),
			reference_docname=kwargs.get("reference_docname"),
			sub_gateway=sub_gateway,
			amount=amount,
			currency=currency,
			mobile_no=mobile_no,
		)

		query = {
			"transaction_id": transaction_id,
			"integration_request": integration_request.name,
			"reference_doctype": kwargs.get("reference_doctype"),
			"reference_docname": kwargs.get("reference_docname"),
			"amount": amount,
			"currency": currency,
		}
		return get_url("/plutu-otp?" + urlencode(query))

	@staticmethod
	def _update_integration_request(integration_request, **data):
		integration_request_dict = frappe.parse_json(integration_request.data) if integration_request.data else {}
		integration_request_dict.update({key: value for key, value in data.items() if value is not None})
		integration_request.db_set("data", frappe.as_json(integration_request_dict), update_modified=False)


def get_integration_request_by_transaction(transaction_id):
	if not transaction_id:
		frappe.throw(_("Missing Plutu transaction ID"))

	integration_requests = frappe.get_all(
		"Integration Request",
		filters={
			"integration_request_service": "Plutu",
			"data": ["like", f'%"transaction_id": "{transaction_id}"%'],
		},
		fields=["name"],
		order_by="creation desc",
		limit=1,
	)
	if not integration_requests:
		frappe.throw(_("No Integration Request found for this Plutu transaction"))

	return frappe.get_doc("Integration Request", integration_requests[0].name)


def handle_payment_success(integration_request_doc):
	"""Mark the Integration Request Completed and run on_payment_authorized on the reference doc.

	NOTE: ERPNext's Payment Request posts the Payment Entry from on_payment_authorized itself —
	this controller must never create a Payment Entry directly.
	"""
	data = frappe.parse_json(integration_request_doc.data) if integration_request_doc.data else {}
	reference_doctype = data.get("reference_doctype")
	reference_docname = data.get("reference_docname")

	integration_request_doc.db_set("status", "Completed", update_modified=False)
	frappe.db.commit()

	redirect_to = None
	if reference_doctype and reference_docname:
		try:
			redirect_to = frappe.get_doc(reference_doctype, reference_docname).run_method(
				"on_payment_authorized", "Completed"
			)
		except Exception:
			frappe.log_error(frappe.get_traceback())

	redirect_url = f"payment-success?doctype={reference_doctype}&docname={reference_docname}"
	if redirect_to:
		redirect_url += "&" + urlencode({"redirect_to": redirect_to})

	return {"redirect_to": redirect_url, "status": "Completed"}


def handle_payment_failure(integration_request_doc, reason=""):
	data = frappe.parse_json(integration_request_doc.data) if integration_request_doc.data else {}
	reference_doctype = data.get("reference_doctype")
	reference_docname = data.get("reference_docname")

	integration_request_doc.db_set("status", "Failed", update_modified=False)
	if reason:
		integration_request_doc.db_set("error", reason, update_modified=False)
	frappe.db.commit()

	redirect_url = f"payment-failed?doctype={reference_doctype}&docname={reference_docname}"
	return {"redirect_to": redirect_url, "status": "Failed"}


@frappe.whitelist(allow_guest=True)
def callback():
	"""Return-URL / webhook target for the redirect sub-gateways (Local Bank Cards, MPGS, T-Lync).

	TODO(bench): confirm the exact query/body params Plutu sends back on the return_url against
	real Plutu docs/sandbox — this assumes `transaction_id` + `status` land in frappe.form_dict,
	mirroring paymob_settings.callback(). Adjust the field names once verified.
	"""
	try:
		transaction_id = frappe.form_dict.get("transaction_id")
		status = str(frappe.form_dict.get("status", "")).lower()

		integration_request_doc = get_integration_request_by_transaction(transaction_id)

		is_payment_successful = status in ("success", "completed", "paid", "captured")

		if is_payment_successful:
			return handle_payment_success(integration_request_doc)
		else:
			frappe.log_error(frappe.get_traceback(), "Plutu Payment not authorized")
			return handle_payment_failure(integration_request_doc, reason=f"Plutu status: {status}")

	except Exception:
		frappe.log_error(frappe.get_traceback(), "Plutu Callback Error")


@frappe.whitelist(allow_guest=True)
def plutu_confirm_otp(transaction_id, otp, integration_request=None, **kwargs):
	"""Called by the plutu-otp portal page once the payer enters the OTP they received."""
	try:
		if integration_request:
			integration_request_doc = frappe.get_doc("Integration Request", integration_request)
		else:
			integration_request_doc = get_integration_request_by_transaction(transaction_id)

		data = frappe.parse_json(integration_request_doc.data) if integration_request_doc.data else {}
		sub_gateway = data.get("sub_gateway") or "Sadad"
		amount = data.get("amount")
		currency = data.get("currency") or "LYD"

		if not amount:
			frappe.throw(_("Missing amount on Plutu Integration Request"))

		gateway_settings = frappe.get_single("Plutu Settings")
		gateway_path = gateway_settings._gateway_path(sub_gateway)
		amount_str = str(int(round(float(amount) * 1000)))

		payload = {
			"transaction_id": transaction_id,
			"otp": otp,
			"amount": amount_str,
			"currency": currency.lower(),
		}

		response = make_post_request(
			url=BASE_URL + gateway_path + "/confirm", json=payload, headers=gateway_settings._headers()
		)

		# TODO(bench): confirm the exact success indicator Plutu's /confirm response uses.
		if not response or str(response.get("status", "")).lower() not in ("completed", "success"):
			frappe.log_error(frappe.get_traceback(), "Plutu OTP Confirmation Failed")
			return handle_payment_failure(
				integration_request_doc, reason=frappe.as_json(response) if response else "No response from Plutu"
			)

		return handle_payment_success(integration_request_doc)

	except Exception:
		frappe.log_error(frappe.get_traceback(), "Plutu OTP Confirmation Error")
		frappe.throw(_("Could not confirm OTP with Plutu"))
