/* Thousand separators in money inputs.
 *
 * A number input cannot show a comma, so money boxes are switched to text with
 * a decimal keypad, grouped as the user types, and stripped back to a plain
 * number on submit so the server still receives 12345.67.
 *
 * Applies to inputs marked data-amount, and to money-looking fields by name
 * (amount, price, rate, debit, credit, salary, ...). Opt out with data-no-amount.
 */
(function () {
  const MONEY_NAME = /(amount|price|rate|salary|wage|debit|credit|total|balance|cost|value|fee|charge|discount|tax|paid|payable|receivable|opening|closing)/i;

  function isMoney(input) {
    if (input.dataset.noAmount !== undefined) return false;
    // Read-only totals are written by their own page's script, which formats them.
    if (input.readOnly || input.disabled) return false;
    if (input.dataset.amount !== undefined) return true;
    if (input.type !== "number" && input.type !== "text") return false;
    if (input.classList.contains("amount-input")) return true;
    return MONEY_NAME.test(input.name || "") || MONEY_NAME.test(input.id || "");
  }

  function group(whole) {
    return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  // Keeps a half-typed value usable: "1234." and "12.5" both survive a keystroke.
  function format(raw) {
    const negative = raw.trim().startsWith("-");
    let cleaned = raw.replace(/[^\d.]/g, "");
    const dot = cleaned.indexOf(".");
    if (dot !== -1) cleaned = cleaned.slice(0, dot + 1) + cleaned.slice(dot + 1).replace(/\./g, "");
    if (!cleaned) return "";
    const [whole, fraction] = cleaned.split(".");
    const text = group(whole || "0") + (fraction !== undefined ? "." + fraction.slice(0, 2) : "");
    return (negative ? "-" : "") + text;
  }

  function plain(value) {
    return (value || "").replace(/,/g, "");
  }

  function caretFromEnd(input) {
    return input.value.length - (input.selectionEnd || 0);
  }

  function enhance(input) {
    if (input.dataset.amountReady) return;
    input.dataset.amountReady = "1";
    // The step/min validation goes with the number type, so the value is
    // checked here instead of by the browser.
    input.dataset.amountMin = input.min || "";
    input.type = "text";
    input.inputMode = "decimal";
    input.autocomplete = "off";
    input.value = format(input.value);

    input.addEventListener("input", () => {
      const tail = caretFromEnd(input);
      input.value = format(input.value);
      const caret = Math.max(0, input.value.length - tail);
      input.setSelectionRange(caret, caret);
    });
    input.addEventListener("blur", () => {
      const value = plain(input.value);
      if (value === "" || isNaN(Number(value))) return;
      input.value = format(Number(value).toFixed(2));
    });
    // Selecting the box for retyping should not fight the grouping.
    input.addEventListener("focus", () => input.select());
  }

  function scan(root) {
    (root || document).querySelectorAll("input").forEach(input => {
      if (isMoney(input)) enhance(input);
    });
  }

  // Forms post the raw number; the commas are put back so the screen is
  // unchanged if validation bounces the page back.
  document.addEventListener("submit", (event) => {
    event.target.querySelectorAll('input[data-amount-ready="1"]').forEach(input => {
      const shown = input.value;
      input.value = plain(shown);
      setTimeout(() => { input.value = shown; }, 0);
    });
  }, true);

  // Rows cloned into an entry grid arrive after load, so new inputs are picked up.
  const observer = new MutationObserver(mutations => {
    mutations.forEach(m => m.addedNodes.forEach(node => {
      if (node.nodeType !== 1) return;
      if (node.tagName === "INPUT") { if (isMoney(node)) enhance(node); return; }
      scan(node);
    }));
  });

  function start() {
    scan(document);
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();

  // Scripts that read a money box themselves (totals, previews) use this.
  window.amountValue = (input) => parseFloat(plain(input && input.value)) || 0;
  window.formatAmount = format;
})();
