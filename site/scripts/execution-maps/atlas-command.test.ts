import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { commandMetadata } from './atlas-command';
import { commandDescription } from './atlas-model';
const root=new URL('../../../',import.meta.url);
describe('canonical skill-entry command metadata',()=>{
  it('resolves the real ADR wrapper to its exact skill owner',()=>{
    const calls:string[]=[];
    const result=commandMetadata('adr',path=>{calls.push(path);return readFileSync(new URL(path,root),'utf8');});
    expect(calls).toEqual(['core/surface/commands/adr.md','core/surface/skills/decision-lifecycle/SKILL.md']);
    expect(result.path).toBe(calls[1]);
    expect(result.description).toBe(commandDescription(readFileSync(new URL(calls[1],root),'utf8')));
  });
  it('checks both inputs and propagates an owning-source refusal',()=>{
    const calls:string[]=[];
    expect(()=>commandMetadata('adr',path=>{calls.push(path);if(calls.length===1)return '{{SKILL_ENTRY:decision-lifecycle}}';throw new Error('source drift');})).toThrow('source drift');
    expect(calls).toHaveLength(2);
  });
  it('does not interpret embedded, malformed or recursive directives',()=>{
    for(const raw of ['{{SKILL_ENTRY:../../elsewhere}}','{{SKILL_ENTRY:debug}}\nextra content','{{SKILL_ENTRY:bad/name}}']){
      let count=0;expect(()=>commandMetadata('debug',()=>{count++;return raw;})).toThrow(/Atlas description/);expect(count).toBe(1);
    }
    let count=0;expect(()=>commandMetadata('debug',()=>{count++;return '{{SKILL_ENTRY:debug}}';})).toThrow(/Atlas description/);expect(count).toBe(2);
  });
  it('accepts BOM/CRLF and preserves an ordinary command description',()=>{
    const direct=commandMetadata('fix',()=> '\uFEFF---\r\ndescription: Direct command.\r\n---\r\n');
    expect(direct).toEqual({path:'core/surface/commands/fix.md',description:'Direct command.'});
    expect(()=>commandMetadata('../escape',()=>{throw new Error('must not read');})).toThrow(/Invalid atlas entry/);
  });
});
