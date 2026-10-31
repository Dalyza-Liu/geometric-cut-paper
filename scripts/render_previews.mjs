import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const args=process.argv.slice(2), root=path.resolve(args[0]);
const moduleFlag=args.indexOf('--modules');
const require=moduleFlag>=0?createRequire(path.join(path.resolve(args[moduleFlag+1]),'__skill_runtime__.cjs')):createRequire(import.meta.url);
let sharp;
try {sharp=require('sharp');} catch {throw new Error('PNG export requires an existing sharp installation; pass --node-modules or use --svg-only.');}
const cache=new Map();
async function render(file,size){
  let svg=fs.readFileSync(file,'utf8');
  const pattern=svg.match(/<pattern\b[^>]*id="series-grain"[\s\S]*?<\/pattern>/);
  if(!pattern)throw new Error('Canonical vector grain is missing: '+file);
  if(!cache.has(pattern[0])){
    const inner=pattern[0].replace(/^<pattern[^>]*>/,'').replace(/<\/pattern>$/,'');
    const tile=`<svg xmlns="http://www.w3.org/2000/svg" width="224" height="224" viewBox="0 0 112 112">${inner}</svg>`;
    const png=await sharp(Buffer.from(tile)).png().toBuffer();
    cache.set(pattern[0],`<pattern id="series-grain" width="112" height="112" patternUnits="userSpaceOnUse"><image href="data:image/png;base64,${png.toString('base64')}" width="112" height="112"/></pattern>`);
  }
  // Only the in-memory PNG render uses a cached tile. The delivered SVG stays fully vector.
  svg=svg.replace(pattern[0],cache.get(pattern[0]));
  let pipeline=sharp(Buffer.from(svg));
  if(size)pipeline=pipeline.resize(size,size,{fit:'inside'});
  const dest=file.replace(/\.svg$/,'.png');
  await pipeline.png().toFile(dest);
  const metadata=await sharp(dest).metadata();
  if(!metadata.hasAlpha)throw new Error('Alpha channel missing: '+dest);
}
await render(path.join(root,'overview.svg'));
for(const name of fs.readdirSync(path.join(root,'individual')).filter(n=>n.endsWith('.svg'))){
  await render(path.join(root,'individual',name),800);
}
process.stdout.write('Rendered overview and transparent individual PNGs; native SVGs unchanged.\n');
