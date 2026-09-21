/* Party balance chip beside a supplier/customer picker.
 *
 * Each <option> carries data-balance (signed: positive = normal side, owed to
 * a supplier or due from a customer). The chip is written on pick and once at
 * load, because the screen can open with a party already chosen.
 *
 *   <select id="supplier" data-balance-chip="supplier-balance" data-balance-owed="Balance" data-balance-credit="In credit">
 *   <p id="supplier-balance" class="bal-chip hidden"></p>
 */
(function () {
  const money = n => (Math.round((Number(n) || 0) * 100) / 100)
    .toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  function write(select, chip) {
    const option = select.options[select.selectedIndex];
    const raw = option ? option.dataset.balance : "";
    if (!select.value || raw === "" || raw === undefined) {
      chip.classList.add("hidden");
      return;
    }
    const amount = Number(raw) || 0;
    chip.classList.remove("hidden");
    chip.classList.toggle("bal-chip--owed", amount > 0);
    chip.classList.toggle("bal-chip--credit", amount < 0);
    chip.textContent = amount < 0
      ? (select.dataset.balanceCredit || "In credit") + ": " + money(Math.abs(amount))
      : (select.dataset.balanceOwed || "Balance") + ": " + money(amount);
  }

  function init(root) {
    (root || document).querySelectorAll("select[data-balance-chip]").forEach(select => {
      const chip = document.getElementById(select.dataset.balanceChip);
      if (!chip || select.dataset.balanceBound) return;
      select.dataset.balanceBound = "1";
      select.addEventListener("change", () => write(select, chip));
      write(select, chip);
    });
  }

  window.PartyBalance = { init };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => init());
  else init();
})();
