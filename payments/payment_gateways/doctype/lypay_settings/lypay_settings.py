# Copyright (c) 2026, SWE Pioneers and contributors
# For license information, please see license.txt

from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.integrations.utils import create_request_log, make_get_request, make_post_request
from frappe.model.document import Document
from frappe.utils import flt, get_url, now_datetime

from payments.utils import create_payment_gateway

DEFAULT_BASE_URL = "http://127.0.0.1:8080"


class LyPaySettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		lypay_base_url: DF.Data | None
		lypay_bearer_token: DF.Password | None
		lypay_creditor_iban: DF.Data | None
		lypay_creditor_name: DF.Data | None
		lypay_debtor_iban: DF.Data | None
		lypay_debtor_name: DF.Data | None
		lypay_email: DF.Data | None
		lypay_institution_code: DF.Data | None
		lypay_institution_name: DF.Data | None
		lypay_merchant_reference_prefix: DF.Data | None
		lypay_password: DF.Password | None
		lypay_token_name: DF.Data | None
		redirect_to: DF.Data | None
	# end: auto-generated types

	def on_update(self):
		create_payment_gateway("LyPay")

	def validate_transaction_currency(self, currency):
		if currency != "LYD":
			frappe.throw(
				_(
					"Please select another payment method. LyPay only supports transactions in Libyan Dinar (LYD)."
				)
			)

	def get_base_url(self):
		return (self.lypay_base_url or DEFAULT_BASE_URL).rstrip("/")

	def _headers(self):
		return {
			"Authorization": f"Bearer {self.get_valid_token()}",
			"Content-Type": "application/json",
			"Accept": "application/json",
		}

	def get_valid_token(self):
		token = self.get_password("lypay_bearer_token", raise_exception=False) if self.lypay_bearer_token else None
		if token:
			return token

		return self.authenticate()

	def authenticate(self):
		"""Authenticate against LyPay and persist the bearer token."""

		payload = {
			"email": self.lypay_email,
			"password": self.get_password("lypay_password", raise_exception=False),
			"token_name": self.lypay_token_name or "frappe-gateway",
			"token_expiration_date": "2099-12-31",
		}

		try:
			response = make_post_request(
				url=f"{self.get_base_url()}/api/v1/auth/token",
				json=payload,
				headers={"Content-Type": "application/json"},
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "LyPay Authentication Error")
			frappe.throw(_("Could not authenticate with LyPay"))

		token = (response or {}).get("data", {}).get("token") or (response or {}).get("token")
		if not token:
			frappe.throw(_("LyPay authentication did not return a token"))

		self.db_set("lypay_bearer_token", token, update_modified=False)
		return token

	@frappe.whitelist()
	def refresh_bearer_token(self):
		"""Manually refresh the LyPay bearer token (e.g. from the settings form)."""

		return self.authenticate()

	@staticmethod
	def format_amount(amount):
		"""LyPay amounts are integers denominated in thousandths of a Dinar."""

		return str(int(round(flt(amount) * 1000)))

	def get_payment_url(self, **kwargs):
		try:
			if not kwargs.get("reference_docname") or not kwargs.get("amount"):
				frappe.throw(_("Missing reference document or amount"))

			integration_request = create_request_log(kwargs, service_name="LyPay")

			merchant_prefix = self.lypay_merchant_reference_prefix or "FRAPPE"
			internal_merchant_reference = f"{merchant_prefix}-{kwargs.get('reference_docname')}"

			payload = {
				"transactionType": "P2M",
				"initiation": {
					"amount": {
						"amount": self.format_amount(kwargs.get("amount")),
						"currency": "lyd",
					},
					"debtorAccount": {
						"schemeName": "iban",
						"identification": self.lypay_debtor_iban,
						"name": self.lypay_debtor_name,
					},
					"creditorAccount": {
						"schemeName": "iban",
						"identification": self.lypay_creditor_iban,
						"name": self.lypay_creditor_name,
					},
					"creditorInstitution": {
						"name": self.lypay_institution_name,
						"code": self.lypay_institution_code,
					},
					"additionalData": {
						"billNumber": kwargs.get("reference_docname") or "",
						"mobileNumber": kwargs.get("payer_email") or "",
						"storeLabel": "Frappe ERP",
						"referenceLabel": kwargs.get("reference_doctype") or "",
						"customerLabel": kwargs.get("payer_email") or "",
						"terminalLabel": "",
						"purposeOfTransaction": f"Payment for {kwargs.get('reference_doctype')} {kwargs.get('reference_docname')}",
					},
					"description": f"Payment for {kwargs.get('reference_doctype')} {kwargs.get('reference_docname')}",
					"internalMerchantReference": internal_merchant_reference,
				},
			}

			response = make_post_request(
				url=f"{self.get_base_url()}/api/v1/payments/funds-transfers",
				json=payload,
				headers=self._headers(),
			)

			data = (response or {}).get("data", {})
			uuid = data.get("uuid")
			payment_reference = data.get("paymentReference")

			if not uuid or not payment_reference:
				frappe.throw(_("Failed to initiate LyPay transfer"))

			integration_request_dict = frappe.parse_json(integration_request.data)
			integration_request_dict.update(
				{
					"lypay_uuid": uuid,
					"lypay_payment_reference": payment_reference,
					"lypay_internal_merchant_reference": internal_merchant_reference,
					"reference_doctype": kwargs.get("reference_doctype"),
					"reference_docname": kwargs.get("reference_docname"),
					"redirect_to": kwargs.get("redirect_to"),
				}
			)
			integration_request.data = frappe.as_json(integration_request_dict)
			integration_request.reference_doctype = kwargs.get("reference_doctype")
			integration_request.reference_docname = kwargs.get("reference_docname")
			integration_request.save(ignore_permissions=True)
			frappe.db.commit()

			return get_url(
				"./lypay-confirm?"
				+ urlencode(
					{
						"integration_request": integration_request.name,
						"uuid": uuid,
						"payment_reference": payment_reference,
						"amount": kwargs.get("amount"),
						"currency": kwargs.get("currency", "LYD"),
						"reference_doctype": kwargs.get("reference_doctype") or "",
						"reference_docname": kwargs.get("reference_docname") or "",
					}
				)
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "LyPay Payment URL Error")
			frappe.throw(_("Could not generate LyPay payment URL"))

	def confirm_transfer(self, uuid, payment_reference, transaction_timestamp):
		response = make_post_request(
			url=f"{self.get_base_url()}/api/v1/payments/funds-transfers/{uuid}/confirm",
			json={
				"paymentReference": payment_reference,
				"transactionTimestamp": int(transaction_timestamp),
			},
			headers=self._headers(),
		)
		data = (response or {}).get("data", {})
		status_name = (data.get("status") or {}).get("name")

		return {
			"status": "Completed" if status_name in ("completed", "acknowledged") else "Pending",
			"raw_response": data,
		}

	def get_transfer_status(self, uuid):
		response = make_get_request(
			url=f"{self.get_base_url()}/api/v1/payments/funds-transfers/{uuid}",
			headers=self._headers(),
		)
		return (response or {}).get("data", {})

	def refund_transfer(self, uuid, payment_reference, transaction_timestamp, amount=None):
		payload = {
			"paymentReference": payment_reference,
			"transactionTimestamp": int(transaction_timestamp),
		}
		if amount:
			payload["amount"] = self.format_amount(amount)

		return make_post_request(
			url=f"{self.get_base_url()}/api/v1/payments/funds-transfers/{uuid}/refund",
			json=payload,
			headers=self._headers(),
		)


def get_lypay_settings():
	return frappe.get_single("LyPay Settings")


def get_integration_request(integration_request):
	if not integration_request:
		frappe.throw(_("Missing integration request"))

	return frappe.get_doc("Integration Request", integration_request)


@frappe.whitelist(allow_guest=True)
def confirm_payment(integration_request, transaction_timestamp=None):
	"""Confirm a LyPay funds transfer. Called from the lypay-confirm portal page
	once the payer has completed the instant-payment transfer in their banking app."""

	integration_request_doc = get_integration_request(integration_request)
	data = frappe.parse_json(integration_request_doc.data)

	uuid = data.get("lypay_uuid")
	payment_reference = data.get("lypay_payment_reference")
	if not uuid or not payment_reference:
		frappe.throw(_("This LyPay transfer was not initiated correctly"))

	settings = get_lypay_settings()
	timestamp = transaction_timestamp or int(now_datetime().timestamp())

	try:
		result = settings.confirm_transfer(uuid, payment_reference, timestamp)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "LyPay Confirm Error")
		integration_request_doc.db_set("status", "Failed", update_modified=False)
		integration_request_doc.db_set("error", frappe.get_traceback(), update_modified=False)
		frappe.db.commit()
		frappe.throw(_("Could not confirm LyPay transfer"))

	data["lypay_raw_confirm_response"] = result.get("raw_response")
	integration_request_doc.data = frappe.as_json(data)

	if result.get("status") == "Completed":
		integration_request_doc.status = "Completed"
		integration_request_doc.save(ignore_permissions=True)
		frappe.db.commit()

		return handle_payment_success(integration_request_doc)

	integration_request_doc.status = "Failed"
	integration_request_doc.error = _("LyPay transfer not confirmed: {0}").format(result.get("status"))
	integration_request_doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {"status": "Failed"}


def handle_payment_success(integration_request_doc):
	"""Handle post-success payments. Delegates to the reference document's
	`on_payment_authorized` hook, which is what actually creates the Payment Entry
	(e.g. via ERPNext's Payment Request) — we never create it here."""

	data = frappe.parse_json(integration_request_doc.data)
	reference_doctype = integration_request_doc.reference_doctype or data.get("reference_doctype")
	reference_docname = integration_request_doc.reference_docname or data.get("reference_docname")
	redirect_to = data.get("redirect_to")

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


@frappe.whitelist(allow_guest=True)
def get_status(integration_request):
	integration_request_doc = get_integration_request(integration_request)
	data = frappe.parse_json(integration_request_doc.data)

	uuid = data.get("lypay_uuid")
	if not uuid:
		frappe.throw(_("This LyPay transfer was not initiated correctly"))

	settings = get_lypay_settings()
	return settings.get_transfer_status(uuid)


@frappe.whitelist()
def refund_payment(integration_request, amount=None):
	"""Refund a LyPay transfer. Restricted to logged-in users with access to
	Integration Request (System Manager / Accounts Manager / Accounts User)."""

	if frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	integration_request_doc = get_integration_request(integration_request)
	data = frappe.parse_json(integration_request_doc.data)

	uuid = data.get("lypay_uuid")
	payment_reference = data.get("lypay_payment_reference")
	if not uuid or not payment_reference:
		frappe.throw(_("This LyPay transfer was not initiated correctly"))

	settings = get_lypay_settings()
	timestamp = int(now_datetime().timestamp())
	response = settings.refund_transfer(uuid, payment_reference, timestamp, amount=amount)

	data["lypay_raw_refund_response"] = response
	integration_request_doc.data = frappe.as_json(data)
	integration_request_doc.save(ignore_permissions=True)
	frappe.db.commit()

	return response
