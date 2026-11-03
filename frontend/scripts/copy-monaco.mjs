import { readFileSync, writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';
import { build } from 'esbuild';

// Monaco vendors DOMPurify in addition to its npm dependency. Rebuild from ESM
// with the audited sanitizer; merely overriding package.json would leave old
// sanitizer code in Monaco's prebuilt browser distribution.
const target = resolve('public/monaco');
const expected = resolve('public') + '/';
if (!target.replaceAll('\\', '/').startsWith(expected.replaceAll('\\', '/'))) throw new Error('Unsafe editor asset directory');
rmSync(target, {recursive:true, force:true});
mkdirSync(target, {recursive:true});
const sanitized = readFileSync('node_modules/dompurify/dist/purify.es.mjs', 'utf8');
if (!sanitized.includes('DOMPurify 3.4.17')) throw new Error('Review sanitizer version before updating editor build');
writeFileSync('node_modules/monaco-editor/esm/vs/base/browser/dompurify/dompurify.js', sanitized);
await build({entryPoints:['node_modules/monaco-editor/esm/vs/editor/editor.main.js'], bundle:true, format:'iife', globalName:'monaco', outfile:target+'/editor.js', minify:true, loader:{'.ttf':'file'}, assetNames:'assets/[name]-[hash]', logLevel:'warning'});
for (const [name, entry] of Object.entries({editor:'editor/editor.worker',json:'language/json/json.worker',css:'language/css/css.worker',html:'language/html/html.worker',ts:'language/typescript/ts.worker'})) {
  await build({entryPoints:[`node_modules/monaco-editor/esm/vs/${entry}.js`],bundle:true,format:'iife',outfile:`${target}/${name}.worker.js`,minify:true,logLevel:'warning'});
}
