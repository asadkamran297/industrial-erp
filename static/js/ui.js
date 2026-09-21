/* Shared screen behavior for every portal page (docs/UI_SYSTEM.md). */
(function () {
  "use strict";

  const FIELD_SELECTOR = [
    "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=checkbox]):not([type=radio]):not([readonly]):not(.searchable-select-search)",
    "select:not(.sr-only):not([data-searchable-enhanced])",
    "textarea",
    ".searchable-select-button",
  ].join(",");

  const visible = (el) => !el.disabled && el.offsetParent !== null && !el.closest("[hidden], .searchable-select-panel, [data-modal].is-closed");

  function formFields(form) {
    const outside = form.id ? Array.from(document.querySelectorAll(`[form="${form.id}"]`)) : [];
    return outside.concat(Array.from(form.querySelectorAll(FIELD_SELECTOR))).filter(visible);
  }

  function saveButton(form) {
    const scoped = form.id ? document.querySelector(`[form="${form.id}"][data-save]`) : null;
    return scoped || form.querySelector("[data-save]") || form.querySelector("button[type=submit]:not([name])");
  }

  function isEntryForm(form) {
    return form && (form.method || "").toLowerCase() === "post" && !form.hasAttribute("data-own-keys") && !form.closest("[data-modal], .filter-bar");
  }

  // Enter moves to the next field; on the last one it lands on Save.
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey || event.defaultPrevented) return;
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.tagName === "TEXTAREA") return;
    if (target.tagName === "BUTTON" && !target.classList.contains("searchable-select-button")) return;
    if (target.closest('.searchable-select[data-open="true"]')) return;
    const form = target.form || target.closest("form");
    if (!isEntryForm(form)) return;
    const fields = formFields(form);
    const index = fields.indexOf(target);
    if (index === -1) return;
    event.preventDefault();
    const next = fields[index + 1];
    if (next) {
      next.focus();
      if (typeof next.select === "function" && next.tagName === "INPUT") next.select();
    } else {
      const save = saveButton(form);
      if (save) save.focus();
    }
  });

  // Ctrl+S saves the form in front of the user.
  document.addEventListener("keydown", (event) => {
    if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "s") return;
    const active = document.activeElement;
    let form = active && (active.form || active.closest("form"));
    if (!isEntryForm(form)) form = Array.from(document.querySelectorAll("main form[method=post]")).find((f) => isEntryForm(f) && saveButton(f));
    if (!form) return;
    event.preventDefault();
    const save = saveButton(form);
    if (save && !save.disabled) form.requestSubmit(save);
  });

  // "/" focuses the board search.
  document.addEventListener("keydown", (event) => {
    if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
    const active = document.activeElement;
    if (active && (active.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName))) return;
    const search = document.querySelector("[data-board-search]");
    if (!search) return;
    event.preventDefault();
    search.focus();
    search.select();
  });

  // Plain (non-Alpine) modals: data-modal + .is-closed.
  function openModal(modal) {
    modal.classList.remove("is-closed");
    modal.removeAttribute("hidden");
    const first = modal.querySelector(FIELD_SELECTOR + ", [data-confirm-go]");
    if (first) setTimeout(() => first.focus(), 20);
  }
  function closeModal(modal) {
    modal.classList.add("is-closed");
    modal.dispatchEvent(new CustomEvent("modal:closed"));
  }
  window.uiModal = { open: openModal, close: closeModal };

  document.addEventListener("click", (event) => {
    const closer = event.target.closest("[data-modal-close]");
    if (closer) {
      const modal = closer.closest("[data-modal]");
      if (modal) closeModal(modal);
      return;
    }
    const opener = event.target.closest("[data-modal-open]");
    if (opener) {
      const modal = document.getElementById(opener.dataset.modalOpen);
      if (modal) { event.preventDefault(); openModal(modal); }
      return;
    }
    const backdrop = event.target.matches && event.target.matches("[data-modal]:not([x-show])") ? event.target : null;
    if (backdrop) closeModal(backdrop);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const open = Array.from(document.querySelectorAll("[data-modal]:not(.is-closed):not([x-show])")).pop();
    if (open) closeModal(open);
  });

  // Destructive actions go through the shared confirmation dialog.
  //   data-confirm="message"            required
  //   data-post="url"                   POST to this url (csrf added)
  //   data-reason="field_name"          ask for a reason, sent under that name
  //   inside a <form> without data-post the form is submitted
  //   on an <a> without data-post the link is followed
  let pending = null;

  function csrfToken() {
    const input = document.querySelector("input[name=csrfmiddlewaretoken]");
    if (input) return input.value;
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function runPending(reason) {
    if (!pending) return;
    const el = pending;
    pending = null;
    if (el.dataset.post) {
      const form = document.createElement("form");
      form.method = "post";
      form.action = el.dataset.post;
      form.hidden = true;
      const token = document.createElement("input");
      token.type = "hidden";
      token.name = "csrfmiddlewaretoken";
      token.value = csrfToken();
      form.appendChild(token);
      if (el.dataset.reason) {
        const field = document.createElement("input");
        field.type = "hidden";
        field.name = el.dataset.reason;
        field.value = reason;
        form.appendChild(field);
      }
      document.body.appendChild(form);
      form.submit();
      return;
    }
    if (el.tagName === "A") { window.location.href = el.href; return; }
    const form = el.form || el.closest("form");
    if (form) {
      el.dataset.confirmed = "1";
      form.requestSubmit(el.type === "submit" ? el : undefined);
    }
  }

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-confirm]");
    if (!trigger || trigger.dataset.confirmed === "1") return;
    const dialog = document.getElementById("confirm-dialog");
    if (!dialog) {
      if (!window.confirm(trigger.dataset.confirm)) event.preventDefault();
      return;
    }
    event.preventDefault();
    pending = trigger;
    dialog.querySelector("[data-confirm-message]").textContent = trigger.dataset.confirm;
    dialog.querySelector("#confirm-dialog-title").textContent = trigger.getAttribute("title") || trigger.textContent.trim() || "Confirm";
    const reasonBox = dialog.querySelector("[data-confirm-reason]");
    const reasonInput = reasonBox.querySelector("input");
    reasonBox.hidden = !trigger.dataset.reason;
    reasonInput.required = Boolean(trigger.dataset.reason);
    reasonInput.value = "";
    const go = dialog.querySelector("[data-confirm-go]");
    go.textContent = trigger.getAttribute("title") || "Confirm";
    openModal(dialog);
  }, true);

  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-confirm-go]")) return;
    const dialog = document.getElementById("confirm-dialog");
    const reasonInput = dialog.querySelector("[data-confirm-reason] input");
    if (reasonInput.required && !reasonInput.value.trim()) { reasonInput.reportValidity(); return; }
    closeModal(dialog);
    runPending(reasonInput.value.trim());
  });

  // Back button: history when there is some, the given url otherwise.
  document.addEventListener("click", (event) => {
    const back = event.target.closest("[data-back]");
    if (!back || window.history.length <= 1 || !document.referrer.startsWith(window.location.origin)) return;
    event.preventDefault();
    window.history.back();
  });

  // Cancel inside an embedded master screen closes the host modal.
  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-embed-cancel]")) return;
    window.parent.postMessage({ type: "embed:cancel" }, window.location.origin);
  });

  // Table export helpers used by the board.
  function tableRows(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return [];
    const rows = [];
    table.querySelectorAll("tr").forEach((row) => {
      if (row.closest("[hidden]") || row.offsetParent === null) return;
      const cells = Array.from(row.querySelectorAll(":scope > th, :scope > td"))
        .filter((cell) => !cell.hidden && !cell.classList.contains("print-hide") && !cell.classList.contains("actions-col") && !cell.querySelector(".row-actions"))
        .map((cell) => cell.innerText.replace(/\s+/g, " ").trim());
      if (cells.length) rows.push(cells);
    });
    return rows;
  }

  function flash(button, text) {
    const label = button.querySelector("span:last-child");
    if (!label) return;
    const was = label.textContent;
    label.textContent = text;
    setTimeout(() => { label.textContent = was; }, 1500);
  }

  document.addEventListener("click", (event) => {
    const copy = event.target.closest("[data-copy-table]");
    if (copy) {
      const text = tableRows(copy.dataset.copyTable).map((r) => r.join("\t")).join("\n");
      const done = () => flash(copy, "Copied");
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(done);
      } else {
        const box = document.createElement("textarea");
        box.value = text;
        box.className = "sr-only";
        document.body.appendChild(box);
        box.select();
        try { document.execCommand("copy"); done(); } finally { box.remove(); }
      }
      return;
    }
    const csv = event.target.closest("[data-csv-table]");
    if (csv) {
      const quote = (v) => /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
      const text = "﻿" + tableRows(csv.dataset.csvTable).map((r) => r.map(quote).join(",")).join("\r\n");
      const link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
      link.download = (document.querySelector(".page-title")?.textContent.trim() || "export").replace(/\s+/g, "-").toLowerCase() + ".csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      return;
    }
    const print = event.target.closest("[data-print-table]");
    if (print) {
      const rows = tableRows(print.dataset.printTable);
      const esc = (v) => v.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
      const title = esc(document.querySelector(".page-title")?.textContent.trim() || "Export");
      const [head, ...body] = rows;
      const sheet = window.open("", "_blank");
      if (!sheet) return;
      const style = document.querySelector('link[rel=stylesheet][href*="print.css"]')?.href || "/static/dist/print.css";
      sheet.document.write(
        `<!doctype html><html><head><meta charset="utf-8"><title>${title}</title><link rel="stylesheet" href="${style}"></head><body>` +
        `<h1 class="doc-title">${title}</h1><table class="items"><thead><tr>${(head || []).map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>` +
        `<tbody>${body.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></body></html>`
      );
      sheet.document.close();
      sheet.addEventListener("load", () => sheet.print());
    }
  });

  // Column picker for boards without a server-side column set; choice kept per browser.
  const LOCKED_HEAD = ".actions-col, .expand-col, .print-hide, .select-col, [data-locked]";
  function columnKey(tableId) { return `columns:${location.pathname}:${tableId}`; }
  function headCells(table) {
    const rows = Array.from(table.tHead ? table.tHead.rows : []);
    return rows.length ? Array.from(rows[rows.length - 1].cells) : [];
  }
  function applyColumns(table, hidden) {
    Array.from(table.rows).forEach((row) => {
      let col = 0;
      Array.from(row.cells).forEach((cell) => {
        if (cell.dataset.span === undefined) cell.dataset.span = String(cell.colSpan);
        const span = Number(cell.dataset.span);
        let shown = 0;
        for (let i = col; i < col + span; i += 1) if (!hidden.has(i)) shown += 1;
        cell.hidden = shown === 0;
        if (shown > 0) cell.colSpan = shown;
        col += span;
      });
    });
  }
  function initColumnMenu(menu) {
    const tableId = menu.dataset.columnMenu;
    const table = document.getElementById(tableId);
    if (!table) return;
    const heads = headCells(table);
    if (heads.length < 2) return;
    const key = columnKey(tableId);
    const defaults = new Set(heads.map((th, i) => (th.hasAttribute("data-default-off") ? i : -1)).filter((i) => i >= 0));
    let hidden = new Set(defaults);
    try {
      const stored = JSON.parse(localStorage.getItem(key) || "null");
      if (Array.isArray(stored)) hidden = new Set(stored.filter((i) => i < heads.length));
    } catch (e) { /* storage unavailable */ }
    const save = () => { try { localStorage.setItem(key, JSON.stringify(Array.from(hidden))); } catch (e) { /* storage unavailable */ } };
    const render = () => {
      menu.innerHTML = "";
      heads.forEach((th, i) => {
        const label = th.innerText.replace(/\s+/g, " ").trim();
        const locked = !label || th.matches(LOCKED_HEAD);
        const row = document.createElement("label");
        row.className = "settings-check-row" + (locked ? " is-locked" : "");
        const box = document.createElement("input");
        box.type = "checkbox";
        box.className = "check";
        box.checked = !hidden.has(i);
        box.disabled = locked;
        box.addEventListener("change", () => {
          if (box.checked) hidden.delete(i); else hidden.add(i);
          save();
          applyColumns(table, hidden);
        });
        const text = document.createElement("span");
        text.textContent = label || "Actions";
        row.append(box, text);
        menu.appendChild(row);
      });
    };
    const reset = menu.parentElement.querySelector("[data-column-reset]");
    if (reset) reset.addEventListener("click", () => {
      hidden = new Set(defaults);
      try { localStorage.removeItem(key); } catch (e) { /* storage unavailable */ }
      render();
      applyColumns(table, hidden);
    });
    render();
    applyColumns(table, hidden);
    document.addEventListener("htmx:afterSwap", (event) => { if (table.contains(event.target) || event.target === table) applyColumns(table, hidden); });
  }
  document.querySelectorAll("[data-column-menu]").forEach(initColumnMenu);

  // Expandable board rows.
  window.rowFold = function rowFold() {
    return {
      openRows: [],
      isRowOpen(pk) { return this.openRows.includes(pk); },
      toggleRow(pk) {
        this.openRows = this.isRowOpen(pk) ? this.openRows.filter((id) => id !== pk) : this.openRows.concat(pk);
      },
    };
  };

  // Date range control on the board filter bar.
  window.dateRange = function dateRange(from, to) {
    const iso = (d) => [d.getFullYear(), String(d.getMonth() + 1).padStart(2, "0"), String(d.getDate()).padStart(2, "0")].join("-");
    const today = new Date();
    const shift = (days) => { const d = new Date(today); d.setDate(d.getDate() + days); return d; };
    const monthStart = (back) => new Date(today.getFullYear(), today.getMonth() - back, 1);
    const monthEnd = (back) => new Date(today.getFullYear(), today.getMonth() - back + 1, 0);
    const quarterStart = new Date(today.getFullYear(), Math.floor(today.getMonth() / 3) * 3, 1);
    const presets = [
      { key: "all", label: "All dates", from: "", to: "" },
      { key: "today", label: "Today", from: iso(today), to: iso(today) },
      { key: "week", label: "Last 7 days", from: iso(shift(-6)), to: iso(today) },
      { key: "days30", label: "Last 30 days", from: iso(shift(-29)), to: iso(today) },
      { key: "month", label: "This month", from: iso(monthStart(0)), to: iso(today) },
      { key: "lastmonth", label: "Last month", from: iso(monthStart(1)), to: iso(monthEnd(1)) },
      { key: "quarter", label: "This quarter", from: iso(quarterStart), to: iso(today) },
      { key: "year", label: "This year", from: iso(new Date(today.getFullYear(), 0, 1)), to: iso(today) },
    ];
    const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const pretty = (value) => {
      if (!value) return "";
      const [y, m, d] = value.split("-");
      return Number(d) + " " + names[Number(m) - 1] + " " + y;
    };
    return {
      open: false,
      presets,
      from: from || "",
      to: to || "",
      get active() {
        const match = presets.find((p) => p.from === this.from && p.to === this.to);
        return match ? match.key : "custom";
      },
      get label() {
        const named = presets.find((p) => p.key === this.active);
        if (named) return named.label;
        if (this.from && this.to) return pretty(this.from) + " – " + pretty(this.to);
        if (this.from) return "From " + pretty(this.from);
        return "Until " + pretty(this.to);
      },
      pick(preset) { this.from = preset.from; this.to = preset.to; this.apply(); },
      clear() { this.from = ""; this.to = ""; this.apply(); },
      apply() {
        if (this.from && this.to && this.to < this.from) return;
        this.$refs.from.value = this.from;
        this.$refs.to.value = this.to;
        this.open = false;
        this.$refs.from.form.submit();
      },
    };
  };

  // Autofocus the first field on entry screens.
  document.addEventListener("DOMContentLoaded", () => {
    if (document.querySelector("[autofocus]") || window.location.hash) return;
    const form = Array.from(document.querySelectorAll("main form[method=post]")).find((f) => saveButton(f) && !f.closest("[data-modal], .filter-bar, .settings-panel, .form-settings-panel"));
    if (!form) return;
    setTimeout(() => {
      const first = formFields(form).find((el) => !el.value || el.tagName === "SELECT" || el.classList.contains("searchable-select-button"));
      if (first && document.activeElement === document.body) first.focus();
    }, 60);
  });

  // Sidebar keeps its scroll position between pages; first visit lands on the current item.
  document.addEventListener("DOMContentLoaded", () => {
    const nav = document.querySelector("[data-nav-scroll]");
    if (!nav) return;
    const key = "portal-nav-scroll";
    const saved = Number(sessionStorage.getItem(key));
    const current = nav.querySelector("[aria-current=page]");
    if (saved > 0) nav.scrollTop = saved;
    if (current) {
      const top = current.getBoundingClientRect().top - nav.getBoundingClientRect().top;
      if (top < 0 || top + current.offsetHeight > nav.clientHeight) current.scrollIntoView({ block: "center" });
    }
    nav.addEventListener("scroll", () => sessionStorage.setItem(key, String(nav.scrollTop)), { passive: true });
  });

  // Sidebar star toggles a favourite; the header bar updates in place.
  document.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-fav-toggle]");
    if (!btn) return;
    event.preventDefault();
    const leaf = btn.closest("[data-nav-leaf]");
    const bar = document.querySelector("[data-fav-bar]");
    if (!leaf || !bar || btn.disabled) return;
    btn.disabled = true;
    fetch(bar.dataset.toggleUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({ href: leaf.dataset.href }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(({ on }) => {
        leaf.classList.toggle("is-fav", on);
        const chip = bar.querySelector(`[data-href="${CSS.escape(leaf.dataset.href)}"]`);
        if (!on) { if (chip) chip.remove(); return; }
        if (chip) return;
        const a = document.createElement("a");
        a.href = leaf.dataset.href;
        a.className = "fav-chip" + (leaf.querySelector("[aria-current=page]") ? " is-current" : "");
        a.dataset.href = leaf.dataset.href;
        a.innerHTML = btn.querySelector("svg").outerHTML + "<span></span>";
        a.querySelector("span").textContent = leaf.dataset.label;
        bar.appendChild(a);
      })
      .catch(() => {})
      .finally(() => { btn.disabled = false; });
  });

  // Mouse wheel scrolls the favourites bar sideways.
  document.addEventListener("wheel", (event) => {
    const bar = event.target.closest("[data-fav-bar]");
    if (!bar || bar.scrollWidth <= bar.clientWidth || event.deltaY === 0) return;
    event.preventDefault();
    bar.scrollLeft += event.deltaY;
  }, { passive: false });
})();
