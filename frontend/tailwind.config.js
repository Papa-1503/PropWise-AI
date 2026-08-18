export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f0f9ff",
          100: "#e0f2fe",
          200: "#bae6fd",
          300: "#7dd3fc",
          400: "#38bdf8",
          500: "#0ea5e9",
          600: "#0284c7",
          700: "#0369a1",
          800: "#075985",
          900: "#0c4a6e",
        },
        accent: {
          50: "#fdf4ff",
          100: "#fae8ff",
          400: "#e879f9",
          500: "#d946ef",
          600: "#c026d3",
        },
      },
      boxShadow: {
        soft: "0 2px 8px -2px rgba(15, 23, 42, 0.08), 0 4px 16px -4px rgba(15, 23, 42, 0.06)",
        softHover: "0 4px 16px -2px rgba(15, 23, 42, 0.12), 0 8px 24px -4px rgba(15, 23, 42, 0.10)",
      },
      backgroundImage: {
        "app-gradient": "linear-gradient(135deg, #f0f9ff 0%, #fdf4ff 50%, #f0fdfa 100%)",
      },
    },
  },
  plugins: [],
}
