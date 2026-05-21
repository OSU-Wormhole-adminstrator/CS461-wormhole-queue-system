/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
    "./node_modules/flowbite/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        "osu-navy": "#002147",
        "osu-orange": "#D73F09",
        "osu-lavender": "#BBA0CA",
        "osu-blue-light": "#a2ceff",
        "osu-navy-dark": "#1a3a5c",
        "osu-orange-muted": "#f47a52",
        "osu-lavender-dark": "#c9b0d9",
      },
      keyframes: {
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(16px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideDown: {
          "0%": { opacity: "0", transform: "translateY(-10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        flashDrop: {
          "0%": { opacity: "0", transform: "translateY(-8px) scale(0.98)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        ticketSlide: {
          "0%": { opacity: "0", transform: "translateX(-10px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        wiggle: {
          "0%, 100%": { transform: "rotate(0deg)" },
          "20%": { transform: "rotate(-8deg)" },
          "40%": { transform: "rotate(6deg)" },
          "60%": { transform: "rotate(-4deg)" },
          "80%": { transform: "rotate(2deg)" },
        },
        shakeX: {
          "0%, 100%": { transform: "translateX(0)" },
          "20%": { transform: "translateX(-8px)" },
          "40%": { transform: "translateX(8px)" },
          "60%": { transform: "translateX(-5px)" },
          "80%": { transform: "translateX(5px)" },
        },
        urgentFlash: {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.72", transform: "scale(1.03)" },
        },
        heroShift: {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
      },
      animation: {
        "fade-up": "fadeUp 0.55s cubic-bezier(0.22, 1, 0.36, 1) both",
        "slide-down": "slideDown 0.45s cubic-bezier(0.22, 1, 0.36, 1) both",
        "flash-drop": "flashDrop 0.4s cubic-bezier(0.22, 1, 0.36, 1) both",
        "ticket-in": "ticketSlide 0.35s cubic-bezier(0.22, 1, 0.36, 1) both",
        wiggle: "wiggle 0.55s cubic-bezier(0.34, 1.56, 0.64, 1) both",
        shake: "shakeX 0.42s cubic-bezier(0.36, 0, 0.66, -0.56) both",
        flash: "urgentFlash 1.15s ease-in-out 2 both",
        "hero-shift": "heroShift 12s ease infinite",
      },
      transitionTimingFunction: {
        spring: "cubic-bezier(0.34, 1.56, 0.64, 1)",
        smooth: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
  plugins: [
    require("flowbite/plugin"),
    require("@tailwindcss/forms"),
    require("@tailwindcss/typography"),
    require("tailwindcss-animate"),
  ],
};