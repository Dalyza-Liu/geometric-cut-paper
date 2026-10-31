#!/usr/bin/env python3
"""Compose native SVG grocery components and optionally export a checked PNG pack."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent.parent
NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
STYLE = json.loads((ROOT/'assets/style.json').read_text())
CATALOG = {x['id']: x for x in json.loads((ROOT/'assets/catalog.json').read_text())['components']}
FORBIDDEN = {'image','script','foreignObject','filter','linearGradient','radialGradient','style'}
GRAIN_IDS = {'vector-paper-grain','grocery-grain','vector-print-grain','series-grain'}
def tag(name): return '{'+NS+'}'+name
def local(el): return el.tag.split('}')[-1]
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def grain():
    g=STYLE['grain']; state=g['seed']
    def rand():
        nonlocal state
        state=(1664525*state+1013904223)&0xffffffff
        return state/4294967296
    pattern=ET.Element(tag('pattern'),id='series-grain',width=str(g['tile']),height=str(g['tile']),patternUnits='userSpaceOnUse')
    for i in range(g['count']):
        x,y=rand()*g['tile'],rand()*g['tile']
        r=g['radiusMin']+rand()*g['radiusRange']; dark=i%g['darkEvery']==0
        a=g['darkOpacityMin']+rand()*g['darkOpacityRange'] if dark else g['lightOpacityMin']+rand()*g['lightOpacityRange']
        ET.SubElement(pattern,tag('circle'),cx=f'{x:.2f}',cy=f'{y:.2f}',r=f'{r:.2f}',fill=g['dark'] if dark else g['light'],opacity=f'{a:.3f}')
    return pattern

def inspect(root, allowed):
    ids=[]
    for el in root.iter():
        if local(el) in FORBIDDEN: raise ValueError('Not an editable flat-vector component: '+local(el))
        for key,value in el.attrib.items():
            if key.startswith('on'): raise ValueError('SVG event handlers are not supported')
            if key.endswith('href') and not value.startswith('#'): raise ValueError('External SVG reference')
            if key in {'fill','stroke'} and value.startswith('#') and value.upper() not in allowed:
                raise ValueError('Undeclared color '+value+'; use an existing color or declare extraColors')
        if el.get('id'): ids.append(el.get('id'))
    if len(ids)!=len(set(ids)): raise ValueError('Duplicate SVG IDs')

def prepare(path, item_id, allowed, overrides):
    text=path.read_text(encoding='utf-8')
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper(): raise ValueError('SVG declarations are not supported')
    root=ET.fromstring(text)
    if local(root)!='svg': raise ValueError('Source is not an SVG')
    box=[float(x) for x in re.split(r'[\s,]+',root.get('viewBox','').strip())]
    if len(box)!=4 or not all(math.isfinite(x) for x in box) or min(box[2:])<=0: raise ValueError('A finite positive viewBox is required')
    for el in root.iter():
        for key in ['fill','stroke']:
            color=el.get(key)
            if color and color.upper() in overrides: el.set(key,overrides[color.upper()])
    inspect(root,allowed)
    for parent in list(root.iter()):
        for child in list(parent):
            if local(child)=='pattern' and child.get('id') in GRAIN_IDS: parent.remove(child)
            if parent is root and local(child) in {'title','desc'}: parent.remove(child)
    mapping={el.get('id'):item_id+'__'+el.get('id') for el in root.iter() if el.get('id')}
    for el in root.iter():
        for key,value in list(el.attrib.items()):
            if key=='id': el.set(key,mapping[value]); continue
            value=re.sub(r'url\(#([^)]*)\)',lambda m:'url(#'+('series-grain' if m[1] in GRAIN_IDS else mapping.get(m[1],m[1]))+')',value)
            if key.endswith('href') and value.startswith('#'): value='#'+mapping.get(value[1:],value[1:])
            if key in {'aria-labelledby','aria-describedby'}: value=' '.join(mapping.get(x,x) for x in value.split())
            el.set(key,value)
    for parent in list(root.iter()):
        for child in list(parent):
            strength=child.attrib.pop('data-grain',None)
            if strength is not None:
                if local(child) not in {'path','rect','circle','ellipse','polygon'}: raise ValueError('data-grain requires a closed shape')
                a=float(strength)
                if not 0<=a<=1: raise ValueError('data-grain must be between zero and one')
                overlay=copy.deepcopy(child); overlay.attrib.pop('id',None)
                overlay.set('fill','url(#series-grain)'); overlay.set('opacity',str(a)); overlay.attrib.pop('stroke',None)
                parent.insert(list(parent).index(child)+1,overlay)
    return box,list(root)

def svg(width,height,children,background=None,title='Supermarket cut-paper illustrations'):
    root=ET.Element(tag('svg'),width=f'{width:g}',height=f'{height:g}',viewBox=f'0 0 {width:g} {height:g}',role='img')
    ET.SubElement(root,tag('title')).text=title
    defs=ET.SubElement(root,tag('defs')); defs.append(grain())
    if background: ET.SubElement(root,tag('rect'),id='background',width=str(width),height=str(height),fill=background)
    root.extend(copy.deepcopy(children))
    return root

def save(root,path,allowed):
    inspect(root,allowed)
    ids={el.get('id') for el in root.iter() if el.get('id')}
    for el in root.iter():
        for value in el.attrib.values():
            for ref in re.findall(r'url\(#([^)]*)\)',value):
                if ref not in ids: raise ValueError('Unresolved SVG reference: '+ref)
    ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene',nargs='?'); parser.add_argument('--out',type=Path)
    parser.add_argument('--node',default='node'); parser.add_argument('--node-modules')
    parser.add_argument('--svg-only',action='store_true'); parser.add_argument('--list',action='store_true')
    args=parser.parse_args()
    if args.list:
        print('\n'.join(CATALOG)); return
    if not args.scene or not args.out: parser.error('scene and --out are required')
    if args.out.exists(): raise ValueError('Output directory already exists; use a new version')
    scene_path=Path(args.scene).resolve(); scene=json.loads(scene_path.read_text())
    if scene.get('schema')!='supermarket-scene/v1': raise ValueError('Unknown scene schema')
    colors={**STYLE['palette'],**scene.get('extraColors',{})}
    if not all(re.fullmatch(r'#[0-9a-fA-F]{6}',v) for v in colors.values()): raise ValueError('Colors must be #RRGGBB')
    allowed={v.upper() for v in colors.values()}
    overrides={k.upper():v.upper() for k,v in scene.get('paletteOverrides',{}).items()}
    if not all(v in allowed for v in overrides.values()): raise ValueError('Undeclared override color')
    canvas=scene['canvas']; width=float(canvas['width']); height=float(canvas['height'])
    if not all(math.isfinite(v) and v>0 for v in [width,height]): raise ValueError('Invalid canvas')
    bg=canvas.get('background',STYLE.get('defaults',{}).get('overviewBackground','transparent'))
    bg=None if bg=='transparent' else colors.get(bg,bg)
    if bg and bg.upper() not in allowed: raise ValueError('Undeclared background')
    items=scene.get('items',[])
    if not items: raise ValueError('Scene is empty')
    ids=set(); prepared=[]
    for item in items:
        name=item['id']
        if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]*',name) or name in ids: raise ValueError('Invalid/duplicate item ID')
        ids.add(name); source=item['source']
        if source.startswith('catalog:'):
            entry=CATALOG[source.split(':',1)[1]]; path=ROOT/'assets'/entry['file']
            if digest(path)!=entry['sha256']: raise ValueError('Bundled component hash changed: '+name)
        else: path=(scene_path.parent/source).resolve()
        viewbox,children=prepare(path,name,allowed,overrides)
        x,y,w,h=map(float,item['bbox'])
        if not all(math.isfinite(v) for v in [x,y,w,h]) or min(x,y)<0 or min(w,h)<=0 or x+w>width or y+h>height:
            raise ValueError('Item box exceeds canvas: '+name)
        scale=min(w/viewbox[2],h/viewbox[3])
        tx=x+(w-viewbox[2]*scale)/2-viewbox[0]*scale; ty=y+(h-viewbox[3]*scale)/2-viewbox[1]*scale
        group=ET.Element(tag('g'),id=name,transform=f'translate({tx:g} {ty:g}) scale({scale:g})'); group.extend(children)
        prepared.append((item,path,viewbox,children,group))
    out=args.out.resolve(); out.mkdir(parents=True); (out/'individual').mkdir(); (out/'source-assets').mkdir()
    groups=[row[4] for row in prepared]
    save(svg(width,height,groups,bg),out/'overview.svg',allowed)
    save(svg(width,height,groups),out/'overview-transparent.svg',allowed)
    portable=copy.deepcopy(scene); portable['canvas']['background']=bg or 'transparent'; provenance=[]
    for i,(item,path,box,children,group) in enumerate(prepared):
        w,h=box[2:]; g=ET.Element(tag('g'),id=item['id'],transform=f'translate({-box[0]:g} {-box[1]:g})'); g.extend(copy.deepcopy(children))
        save(svg(w,h,[g],title=item.get('label',item['id'])),out/'individual'/(item['id']+'.svg'),allowed)
        target=out/'source-assets'/(item['id']+'.svg'); shutil.copy2(path,target)
        portable['items'][i]['source']='source-assets/'+target.name
        provenance.append({'id':item['id'],'source':item['source'],'sha256':digest(path)})
    (out/'scene.json').write_text(json.dumps(portable,ensure_ascii=False,indent=2)+'\n')
    (out/'provenance.json').write_text(json.dumps({'style_sha256':digest(ROOT/'assets/style.json'),'sources':provenance},ensure_ascii=False,indent=2)+'\n')
    if not args.svg_only:
        cmd=[args.node,str(ROOT/'scripts/render_previews.mjs'),str(out)]
        if args.node_modules: cmd+=['--modules',args.node_modules]
        subprocess.run(cmd,check=True)
    with ZipFile(out/'assets.zip','w',ZIP_DEFLATED) as z:
        for path in sorted(out.rglob('*')):
            if path.is_file() and path.name!='assets.zip': z.write(path,path.relative_to(out))
    print(f'Created {len(items)} grouped vector items in {out}')

if __name__=='__main__':
    try: main()
    except (ValueError,KeyError,ET.ParseError) as exc: raise SystemExit(str(exc))
