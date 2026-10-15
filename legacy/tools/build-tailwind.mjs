// Újragenerálja a fitness_tracker.html-be ágyazott Tailwind CSS-t.
// Akkor kell futtatni, ha a HTML-ben/JS-ben új Tailwind osztályt használsz.
// Használat (a projekt mappájából):  node tools/build-tailwind.mjs
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const htmlPath = join(dirname(fileURLToPath(import.meta.url)), '..', 'fitness_tracker.html');
const START = '/* tailwind:start */';
const END = '/* tailwind:end */';

const workDir = mkdtempSync(join(tmpdir(), 'tw-'));
try {
    const input = join(workDir, 'input.css');
    const output = join(workDir, 'out.css');
    const config = join(workDir, 'tailwind.config.cjs');
    const html = readFileSync(htmlPath, 'utf8');
    const startIdx = html.indexOf(START);
    const endIdx = html.indexOf(END);
    if (startIdx < 0 || endIdx < 0) throw new Error('Nem találom a tailwind:start / tailwind:end jelölőket.');
    const source = html.slice(0, startIdx) + html.slice(endIdx); // a már beágyazott CSS-t nem szkenneljük
    writeFileSync(input, '@tailwind base;\n@tailwind components;\n@tailwind utilities;\n');
    // A tartalmat "raw"-ként adjuk át: a fájl-glob nem kezeli jól az ékezetes/szóközös útvonalakat.
    writeFileSync(config, `module.exports = { content: [{ raw: ${JSON.stringify(source)}, extension: 'html' }] };`);
    execFileSync('npx', ['--yes', 'tailwindcss@3.4.17', '-c', config, '-i', input, '-o', output, '--minify'],
        { stdio: 'inherit', shell: process.platform === 'win32' });

    const css = readFileSync(output, 'utf8').trim();
    const updated = html.slice(0, startIdx + START.length) + '\n' + css + '\n' + html.slice(endIdx);
    writeFileSync(htmlPath, updated);
    console.log(`Kész: ${css.length} bájt Tailwind CSS beágyazva.`);
} finally {
    rmSync(workDir, { recursive: true, force: true });
}
