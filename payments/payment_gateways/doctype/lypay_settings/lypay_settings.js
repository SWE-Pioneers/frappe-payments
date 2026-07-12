// Copyright (c) 2026, SWE Pioneers and contributors
// For license information, please see license.txt

frappe.ui.form.on("LyPay Settings", {
  refresh(frm) {
    frm.add_custom_button(__("Refresh Bearer Token"), () => {
      frm.trigger("refresh_bearer_token");
    });
  },
  refresh_bearer_token: function (frm) {
    try {
      frm
        .call({
          method: "refresh_bearer_token",
          doc: frm.doc,
          freeze: true,
          freeze_message: __("Authenticating with LyPay ..."),
        })
        .then((r) => {
          if (!r.exc && r.message) {
            frm.set_value("lypay_bearer_token", r.message);
            frappe.show_alert({
              message: __("Bearer Token Updated"),
              indicator: "green",
            });
          }
        });
    } catch (e) {
      console.log(e);
    }
  },
});
