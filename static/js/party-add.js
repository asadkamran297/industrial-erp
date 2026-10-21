(function () {
  // "+" beside a party picker: opens the master's embedded form in #entity-modal and drops the saved record into the picker.
  let pending = null;

  const parts = () => {
    const modal = document.getElementById("entity-modal");
    if (!modal) return null;
    return {
      modal,
      frame: document.getElementById("entity-frame"),
      title: document.getElementById("entity-modal-title"),
      card: modal.querySelector(".entity-modal-card"),
    };
  };

  function close() {
    const p = parts();
    if (!p || !pending) return;
    p.modal.hidden = true;
    p.frame.src = "about:blank";
    document.body.style.overflow = "";
    pending = null;
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-party-add]");
    if (button) {
      const p = parts();
      if (!p) return;
      pending = { kind: button.dataset.kind, target: document.getElementById(button.dataset.target) };
      ["md", "xl"].forEach((size) => p.card.classList.remove("entity-modal-card--" + size));
      p.card.classList.add("entity-modal-card--lg");
      p.title.textContent = button.dataset.title;
      p.frame.src = button.dataset.url;
      p.modal.hidden = false;
      document.body.style.overflow = "hidden";
      return;
    }
    if (!pending) return;
    const p = parts();
    if (event.target.closest("#entity-modal-close") || event.target === p.modal) close();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && pending) close();
  });

  window.addEventListener("message", (event) => {
    if (event.origin !== window.location.origin || !pending) return;
    const data = event.data || {};
    if (data.type === "embed:cancel") { close(); return; }
    if (data.type !== pending.kind || !data.record || !pending.target) return;
    const option = new Option(data.record.name, data.record.id, true, true);
    if (data.record.balance) option.dataset.balance = data.record.balance;
    pending.target.add(option);
    pending.target.dispatchEvent(new Event("change", { bubbles: true }));
    close();
  });
})();
