/** Resolve the existing site's tokens for both inline and standalone outputs.
 * This exports CSS values, never font bytes or a second hand-maintained palette. */
export interface AtlasTheme { variables:string; sans:string; bg:string; panel:string; node:string; ink:string; soft:string; muted:string; line:string; flow:string; context:string; conditional:string; return:string; stop:string }
export function atlasTheme(css:string):AtlasTheme {
  const block=/:root\s*\{([^}]+)\}/.exec(css.replace(/\/\*[\s\S]*?\*\//g,''))?.[1];
  if(!block)throw new Error('Missing site design tokens');
  const values=new Map([...block.matchAll(/(--ca-[a-z0-9-]+)\s*:\s*([^;]+);/g)].map(m=>[m[1],m[2].trim()]));
  const resolve=(name:string,seen:string[]=[]):string=>{
    const value=values.get(name);if(!value || seen.includes(name))throw new Error(`Missing/cyclic design token: ${name}`);
    if(/[<>{}]/.test(value) || /url\s*\(/i.test(value))throw new Error(`Unsafe standalone design token: ${name}`);
    return value.replace(/var\((--ca-[a-z0-9-]+)\)/g,(_,key:string)=>resolve(key,[...seen,name]));
  };
  return {variables:[...values.keys()].map(k=>`${k}:${resolve(k)};`).join(''),sans:resolve('--ca-font-sans'),bg:resolve('--ca-bg'),panel:resolve('--ca-bg-raised'),node:resolve('--ca-bg-panel'),ink:resolve('--ca-ink'),soft:resolve('--ca-ink-soft'),muted:resolve('--ca-ink-muted'),line:resolve('--ca-line'),flow:resolve('--ca-info'),context:resolve('--ca-ink-soft'),conditional:resolve('--ca-brand'),return:resolve('--ca-ink-muted'),stop:resolve('--ca-danger')};
}
