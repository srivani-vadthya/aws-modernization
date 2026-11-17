/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["IBM Plex Sans", "Segoe UI", "-apple-system", "BlinkMacSystemFont", "sans-serif"],
        mono: ["IBM Plex Mono", "Consolas", "Monaco", "monospace"],
      },
      colors: {
        ink: {
          950: "#ffffff",
          900: "#f8fafc",
          800: "#f1f5f9",
          700: "#e2e8f0",
          600: "#cbd5e1",
          500: "#64748b",
          400: "#475569",
          300: "#334155",
          200: "#1e293b",
          100: "#0f172a",
        },
        copper: {
          50: "#fef3ee",
          100: "#fde5d7",
          200: "#fbc7ad",
          300: "#c25e24",
          400: "#b45309",
          500: "#9a3412",
          600: "#7c2d12",
        },
      },
      boxShadow: {
        'subtle': '0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px -1px rgba(0, 0, 0, 0.05)',
        'card': '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05)',
      }
    },
  },
  plugins: [],
};
