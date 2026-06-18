(function () {
  function enhanceSelect(select) {
    if (select.dataset.searchableEnhanced === 'true') {
      return;
    }
    select.dataset.searchableEnhanced = 'true';
    select.classList.add('sr-only');
    select.tabIndex = -1;

    const wrapper = document.createElement('div');
    wrapper.className = 'searchable-select relative';
    wrapper.dataset.open = 'false';

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'searchable-select-button';
    button.setAttribute('aria-haspopup', 'listbox');
    button.setAttribute('aria-expanded', 'false');

    const label = document.createElement('span');
    label.className = 'min-w-0 flex-1 truncate text-left';

    const arrow = document.createElement('span');
    arrow.className = 'text-xs text-slate-400';
    arrow.textContent = '>';

    const panel = document.createElement('div');
    panel.className = 'searchable-select-panel hidden';

    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'searchable-select-search';
    search.placeholder = 'Search...';

    const list = document.createElement('div');
    list.className = 'max-h-56 overflow-y-auto py-1';
    list.setAttribute('role', 'listbox');

    button.append(label, arrow);
    panel.append(search, list);
    wrapper.append(button, panel);
    select.after(wrapper);

    function selectedText() {
      const selected = select.options[select.selectedIndex];
      return selected && selected.text ? selected.text : 'Select...';
    }

    function renderOptions() {
      const query = search.value.trim().toLowerCase();
      list.innerHTML = '';
      Array.from(select.options).forEach((option) => {
        const text = option.text || '';
        if (query && !text.toLowerCase().includes(query)) {
          return;
        }
        const item = document.createElement('button');
        item.type = 'button';
        item.className = option.value === select.value ? 'searchable-select-option active' : 'searchable-select-option';
        item.textContent = text;
        item.setAttribute('role', 'option');
        item.setAttribute('aria-selected', option.value === select.value ? 'true' : 'false');
        item.addEventListener('click', () => {
          select.value = option.value;
          select.dispatchEvent(new Event('change', { bubbles: true }));
          closePanel();
          updateLabel();
        });
        list.append(item);
      });
      if (!list.children.length) {
        const empty = document.createElement('p');
        empty.className = 'px-3 py-2 text-sm text-slate-500';
        empty.textContent = 'No results';
        list.append(empty);
      }
    }

    function updateLabel() {
      label.textContent = selectedText();
      renderOptions();
    }

    function openPanel() {
      wrapper.dataset.open = 'true';
      button.setAttribute('aria-expanded', 'true');
      panel.classList.remove('hidden');
      search.value = '';
      renderOptions();
      window.setTimeout(() => search.focus(), 0);
    }

    function closePanel() {
      wrapper.dataset.open = 'false';
      button.setAttribute('aria-expanded', 'false');
      panel.classList.add('hidden');
    }

    button.addEventListener('click', () => {
      wrapper.dataset.open === 'true' ? closePanel() : openPanel();
    });
    search.addEventListener('input', renderOptions);
    select.addEventListener('change', updateLabel);
    document.addEventListener('click', (event) => {
      if (!wrapper.contains(event.target) && event.target !== select) {
        closePanel();
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        closePanel();
      }
    });
    updateLabel();
  }

  function initSearchableSelects() {
    document.querySelectorAll('select.form-select').forEach(enhanceSelect);
  }

  document.addEventListener('DOMContentLoaded', initSearchableSelects);
  document.addEventListener('htmx:afterSettle', initSearchableSelects);
})();
