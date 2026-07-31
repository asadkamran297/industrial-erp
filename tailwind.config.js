module.exports = {
  darkMode: "class",
  content: [
    "./templates/**/*.html",
    "./apps/**/*.py",
    "./static/js/**/*.js"
  ],
  theme: {
    extend: {
      fontFamily: {
        // Drives Preflight's default on <html> and the `font-sans` utility, so
        // every element — form controls included — inherits Inter.
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif"
        ]
      }
    }
  },
  plugins: []
};
