import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

// A public/sw.js-be buildenként új cache-verziót és a hash-elt assetek listáját írjuk:
// a Service Worker telepítéskor előre letölti őket, így az első látogatás után offline is indul az app.
const serviceWorkerManifest = () => {
    let assets = [];
    return {
        name: 'sw-manifest',
        apply: 'build',
        generateBundle(_, bundle) {
            assets = Object.keys(bundle).filter((f) => f.startsWith('assets/')).map((f) => `/${f}`);
        },
        closeBundle() {
            const file = fileURLToPath(new URL('./dist/sw.js', import.meta.url));
            writeFileSync(file, readFileSync(file, 'utf8')
                .replace('__BUILD_ID__', Date.now().toString(36))
                .replace("'__PRECACHE__'", JSON.stringify(assets).slice(1, -1)));
        },
    };
};

export default defineConfig({
    server: {
        // Fejlesztéskor a backend: uvicorn app.main:app --port 8420
        proxy: { '/api': 'http://127.0.0.1:8420' },
    },
    build: { outDir: 'dist', emptyOutDir: true },
    plugins: [serviceWorkerManifest()],
    test: { environment: 'node' },
});
