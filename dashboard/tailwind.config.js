/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['Inter', 'Noto Sans Thai', 'system-ui', 'sans-serif'] },
    },
  },
  plugins: [],
}
