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

  // Printed from a hidden frame rather than a popup window. A popup showed its
  // own window behind the print dialog, and cancelling the dialog left it open
  // because "afterprint" is not fired reliably on cancel. A frame has nothing
  // to leave behind: the dialog is the only thing the user sees, and whether
  // they print or cancel, the frame is thrown away.
  var frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden;";
  document.body.appendChild(frame);

  var done = false;
  function discard() {
    if (done) { return; }
    done = true;
    // After the dialog closes, not during it: removing the frame while it is
    // still printing cancels the job in some browsers.
    window.setTimeout(function () {
      if (frame.parentNode) { frame.parentNode.removeChild(frame); }
    }, 0);
  }

  frame.onload = function () {
    var win = frame.contentWindow;
    win.onafterprint = discard;
    // Nothing fires afterprint in a few browsers; the window regaining focus
    // means the dialog is gone either way.
    window.addEventListener("focus", discard, { once: true });
    win.focus();
    win.print();
  };

  var doc = frame.contentWindow.document;
  doc.open();
  doc.write(html);
  doc.close();
};
