import {build} from 'esbuild';
import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';

const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(here,'../..');
const output=path.join(root,'frontend/live-markdown.js');
const result=await build({absWorkingDir:root,entryPoints:['frontend/live-markdown-source.mjs'],outfile:output,bundle:true,format:'iife',platform:'browser',target:'es2020',minify:true,legalComments:'eof',metafile:true,nodePaths:[path.join(here,'node_modules')]});
const packages=new Map();
for(const input of Object.keys(result.metafile.inputs)) {
  if(!input.includes('node_modules/'))continue;
  let directory=path.dirname(path.resolve(root,input));
  while(directory!==path.dirname(directory)) {
    try {
      const info=JSON.parse(await readFile(path.join(directory,'package.json'),'utf8'));
      if(info.name&&info.version){packages.set(info.name,{directory,info});break;}
    } catch {}
    directory=path.dirname(directory);
  }
}
let notices='YingXu local Markdown editor: bundled third-party licenses\n\n';
const dependencies=[];
for(const [name,{directory,info}] of [...packages].sort(([a],[b])=>a.localeCompare(b))) {
  let license;
  for(const file of ['LICENSE','LICENSE.md','LICENSE.txt','LICENCE']) {
    try {license=await readFile(path.join(directory,file),'utf8');break;}catch{}
  }
  if(!license)throw new Error(`Missing bundled license: ${name}`);
  notices+=`${name} ${info.version} (${info.license})\n${license.trim()}\n\n`;
  dependencies.push({name,version:info.version,license:info.license});
}
await writeFile(path.join(root,'frontend/live-markdown.LICENSE.txt'),notices,'utf8');
const bytes=await readFile(output);
const manifest={file:'live-markdown.js',bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),dependencies};
await writeFile(path.join(root,'frontend/live-markdown.manifest.json'),JSON.stringify(manifest,null,2)+'\n','utf8');
console.log(JSON.stringify({file:manifest.file,bytes:manifest.bytes,sha256:manifest.sha256,dependencies:dependencies.length}));
