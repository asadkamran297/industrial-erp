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

  var html = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>" + title + "</title>" +
    // Styling lives in a real stylesheet, never inline in this string.
    "<link rel='stylesheet' href='/static/dist/print-popup.css'>" +
    "</head><body>" +
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
