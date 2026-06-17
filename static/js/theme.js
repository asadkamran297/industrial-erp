function themeController() {
  return {
    theme: 'light',
    primaryColor: '#2563eb',
    init() {
      const savedTheme = localStorage.getItem('portal-theme');
      const savedColor = localStorage.getItem('portal-primary-color');
      this.theme = savedTheme || document.documentElement.dataset.defaultTheme || 'light';
      const cssColor = getComputedStyle(document.body).getPropertyValue('--primary-color').trim();
      this.primaryColor = this.normalizeColor(savedColor) || this.normalizeColor(cssColor) || '#2563eb';
      this.applyTheme();
      this.setPrimaryColor(this.primaryColor);
    },
    toggleTheme() {
      this.theme = this.theme === 'dark' ? 'light' : 'dark';
      localStorage.setItem('portal-theme', this.theme);
      this.applyTheme();
    },
    applyTheme() {
      document.documentElement.classList.toggle('dark', this.theme === 'dark');
    },
    setPrimaryColor(color) {
      this.primaryColor = this.normalizeColor(color) || '#2563eb';
      document.body.style.setProperty('--primary-color', this.primaryColor);
      localStorage.setItem('portal-primary-color', this.primaryColor);
    },
    normalizeColor(color) {
      return /^#[0-9a-fA-F]{6}$/.test(color || '') ? color : null;
    }
  };
}
