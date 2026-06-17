function themeController() {
  return {
    theme: 'light',
    primaryColor: '#2563eb',
    init() {
      const savedTheme = localStorage.getItem('portal-theme');
      const savedColor = localStorage.getItem('portal-primary-color');
      this.theme = savedTheme || document.documentElement.dataset.defaultTheme || 'light';
      this.primaryColor = savedColor || getComputedStyle(document.body).getPropertyValue('--primary-color').trim() || '#2563eb';
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
      this.primaryColor = color;
      document.body.style.setProperty('--primary-color', color);
      localStorage.setItem('portal-primary-color', color);
    }
  };
}
