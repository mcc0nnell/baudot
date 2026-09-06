import { existsSync, lstatSync, rmSync, symlinkSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = dirname(fileURLToPath(import.meta.url));
const siteRoot = resolve(scriptDir, '..');
const source = resolve(siteRoot, '..', 'testkit');
const link = resolve(siteRoot, 'testkit');

if (!existsSync(source)) {
  throw new Error(`Baudot testkit not found at ${source}`);
}

if (existsSync(link) || (() => { try { lstatSync(link); return true; } catch { return false; } })()) {
  rmSync(link, { recursive: true, force: true });
}

symlinkSync(source, link, process.platform === 'win32' ? 'junction' : 'dir');
console.log(`Linked ${link} -> ${source}`);
