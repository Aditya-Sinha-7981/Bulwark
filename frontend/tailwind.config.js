/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['ui-sans-serif', 'system-ui', 'Segoe UI', 'Roboto', 'Arial', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'Liberation Mono', 'monospace'],
      },
      colors: {
        // Near-black enterprise background
        ink: '#0a0e19',
        // Slightly different dark tone for sidebar / secondary surfaces
        panel: '#0d1424',
        // Dark navy surfaces for cards
        surface: '#131c31',
        elevated: '#1a2642',
        // Subtle blue-gray borders
        line: '#223150',
        lineStrong: '#31466f',
        // Text scale: white primary -> muted gray secondary -> dim
        txt: {
          hi: '#eef2f8',
          mid: '#9fb0c9',
          low: '#6d7f99',
          dim: '#4b5d78',
        },
        // Blue primary action
        accent: {
          DEFAULT: '#4c8dff',
          strong: '#2f6bff',
          hover: '#6ea2ff',
          soft: 'rgba(76, 141, 255, 0.14)',
        },
        // Green = connected / secure / completed
        ok: {
          DEFAULT: '#2ec98c',
          soft: 'rgba(46, 201, 140, 0.12)',
        },
        // Amber warning
        warn: {
          DEFAULT: '#f2b04b',
          soft: 'rgba(242, 176, 75, 0.12)',
        },
        // Red = failed / error
        danger: {
          DEFAULT: '#ef6f6f',
          soft: 'rgba(239, 111, 111, 0.12)',
        },
        // Purple accent for artifacts / special states
        band: {
          DEFAULT: '#a78bfa',
          soft: 'rgba(167, 139, 250, 0.14)',
        },
      },
    },
  },
  plugins: [],
}