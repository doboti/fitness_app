/** @type {import('tailwindcss').Config} */
export default {
    content: ['./index.html', './src/**/*.js'],
    theme: {
        extend: {
            colors: {
                // A téma (férfi zöld / női rózsaszín) CSS változóból jön, így az opacitás-módosítók is működnek (bg-primary/20).
                primary: 'rgb(var(--primary) / <alpha-value>)',
                'primary-strong': 'rgb(var(--primary-strong) / <alpha-value>)',
            },
            fontFamily: { sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'] },
        },
    },
};
