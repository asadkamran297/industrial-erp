window.printSection = function (elementId, title) {
  var el = document.getElementById(elementId);
  if (!el) { console.error("printSection: element not found:", elementId); return; }

  var orgEl = document.getElementById("__org_print_data__");
  var org = orgEl ? JSON.parse(orgEl.textContent) : {};

  var now = new Date();
  var pad = function (n) { return String(n).padStart(2, "0"); };
  var h = now.getHours(), ampm = h >= 12 ? "PM" : "AM";
  h = h % 12 || 12;
  var printed = pad(now.getDate()) + "-" + pad(now.getMonth() + 1) + "-" + now.getFullYear() +
    ", " + h + ":" + pad(now.getMinutes()) + " " + ampm;

  var contactHtml = "";
  if (org.phone)   contactHtml += "<span><b>Phone:</b> " + org.phone + "</span>";
  if (org.cell)    contactHtml += "<span><b>Cell:</b> " + org.cell + "</span>";
  if (org.fax)     contactHtml += "<span><b>Fax:</b> " + org.fax + "</span>";
  if (org.email)   contactHtml += "<span><b>Email:</b> " + org.email + "</span>";
  if (org.website) contactHtml += "<span><b>Website:</b> " + org.website + "</span>";
  contactHtml += "<span class='org-printed'><b>Printed:</b> " + printed + "</span>";

  var logoHtml = org.logo ? "<img src='" + org.logo + "' alt='logo'>" : "";

  var html = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>" + title + "</title><style>" +
    "* { box-sizing: border-box; }" +
    "body { font-family: Arial, Helvetica, sans-serif; color: #111; margin: 24px; font-size: 12px; }" +
    ".org-header { position: relative; text-align: center; border-bottom: 3px double #7a0000; padding-bottom: 12px; margin-bottom: 6px; }" +
    ".org-header img { height: 72px; width: auto; object-fit: contain; margin-bottom: 6px; }" +
    ".org-name { font-size: 26px; font-weight: 800; letter-spacing: .5px; color: #7a0000; text-transform: uppercase; }" +
    ".org-branch { font-size: 12px; font-weight: 600; color: #333; margin-top: 2px; }" +
    ".org-addr { font-size: 11px; color: #555; margin-top: 3px; }" +
    ".org-contact { position: absolute; top: 0; right: 0; text-align: right; font-size: 11px; color: #333; display: flex; flex-direction: column; gap: 2px; }" +
    ".org-contact span { white-space: nowrap; }" +
    ".org-contact b { color: #7a0000; }" +
    ".org-printed { margin-top: 8px; color: #666; }" +
    "h1.doc-title { text-align: center; font-size: 20px; margin: 14px 0; }" +
    "table, table[class] { width: 100% !important; border-collapse: collapse !important; margin-top: 8px; }" +
    "th, td { border: 1px solid #999 !important; padding: 6px 8px !important; font-size: 11px !important; color: #111 !important; background: none; }" +
    "th { background: #f0f0f0 !important; text-align: left !important; font-weight: 600 !important; }" +
    "thead th { text-transform: uppercase; font-size: 10px !important; }" +
    "tr:nth-child(even) td { background: #fafafa !important; }" +
    "button, form, label, input, .peer, [class*='sr-only'] { display: none !important; }" +
    ".footer { margin-top: 30px; border-top: 1px solid #333; padding-top: 8px; text-align: center; font-size: 11px; color: #444; }" +
    ".print-btn { margin-bottom: 14px; }" +
    "@media print { .print-btn { display: none; } body { margin: 0; } }" +
    "</style></head><body>" +
    "<div class='print-btn'><button onclick='window.print()'>Print</button> <button onclick='window.close()'>Close</button></div>" +
    "<div class='org-header'>" +
      logoHtml +
      "<div class='org-name'>" + (org.name || "Organization") + "</div>" +
      (org.branch ? "<div class='org-branch'>" + org.branch + "</div>" : "") +
      (org.address ? "<div class='org-addr'>" + org.address + "</div>" : "") +
      "<div class='org-contact'>" + contactHtml + "</div>" +
    "</div>" +
    "<h1 class='doc-title'>" + title + "</h1>" +
    el.outerHTML +
    "<div class='footer'>" + (org.name || "") + (org.website ? " &middot; " + org.website : "") + " &middot; This is a system generated document.</div>" +
    "</body></html>";

  var w = window.open("", "_blank", "width=1000,height=700");
  w.document.write(html);
  w.document.close();
  w.onload = function () { w.print(); w.onafterprint = function () { w.close(); }; };
};
