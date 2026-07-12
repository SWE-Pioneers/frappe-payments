// Copyright (c) 2026, SWE Pioneers and contributors
// For license information, please see license.txt

frappe.ui.form.on("Moamalat Settings", {
  refresh(frm) {
    frm.dashboard.set_headline(
      __("Moamalat is a Libyan payment gateway. Only LYD transactions are supported.")
    );
  },
});
