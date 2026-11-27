import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mkdtemp, realpath, writeFile, readFile, rm, mkdir, appendFile, rename, link, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
const probe = vi.hoisted(() => ({ wholeReads: 0, readBytes: 0, beforeRead: undefined as undefined | (() => Promise<void>) }));
vi.mock("node:fs/promises", async load => {
 const actual = await load<typeof import("node:fs/promises")>();
 return { ...actual, readFile: (...args:Parameters<typeof actual.readFile>) => { if(String(args[0]).endsWith("Cargo.toml"))probe.wholeReads++;return actual.readFile(...args); },
  open: async (...args:Parameters<typeof actual.open>) => {
   const handle=await actual.open(...args);if(!String(args[0]).endsWith("Cargo.toml"))return handle;
   return new Proxy(handle,{get(target,property){
    if(property==="read")return async (...readArgs:Parameters<typeof handle.read>)=>{const callback=probe.beforeRead;probe.beforeRead=undefined;await callback?.();const result=await target.read(...readArgs);probe.readBytes+=result.bytesRead;return result;};
    if(property==="readFile")return (...readArgs:Parameters<typeof handle.readFile>)=>{probe.wholeReads++;return target.readFile(...readArgs);};
    const value=Reflect.get(target,property);return typeof value==="function"?value.bind(target):value;
   }});
  }};
});
import { inspectNativeProviderInputs, MAX_NATIVE_INPUT_BYTES } from "./build.ts";
let root:string;
const cargo='[package]\nname="fixture"\nversion="1.0.0"\n';
beforeEach(async()=>{root=await realpath(await mkdtemp(path.join(tmpdir(),"ca-native-build-inputs-")));await writeFile(path.join(root,"Cargo.toml"),cargo);probe.wholeReads=0;probe.readBytes=0;probe.beforeRead=undefined;});
afterEach(async()=>{await rm(root,{recursive:true,force:true});});
describe("bounded owned native provider inputs",()=>{
 it("accepts absent optional inputs and the same complete identity across staging basenames",async()=>{
  const second=await realpath(await mkdtemp(path.join(tmpdir(),"ca-native-build-inputs-")));
  try{await writeFile(path.join(second,"Cargo.toml"),cargo);const a=await inspectNativeProviderInputs(root),b=await inspectNativeProviderInputs(second);expect(a).toEqual(b);expect(a).toMatchObject({providers:["rust"],sha256:expect.stringMatching(/^[a-f0-9]{64}$/)});expect(probe.wholeReads).toBe(0);}finally{await rm(second,{recursive:true,force:true});}
 });
 it("accepts exact maximum bytes and refuses known oversized/multibyte input before a payload read",async()=>{
  await writeFile(path.join(root,"Cargo.toml"),cargo+"#"+"x".repeat(MAX_NATIVE_INPUT_BYTES-Buffer.byteLength(cargo)-1));await expect(inspectNativeProviderInputs(root)).resolves.toMatchObject({providers:["rust"]});
  probe.readBytes=0;await appendFile(path.join(root,"Cargo.toml"),"x");await expect(inspectNativeProviderInputs(root)).rejects.toThrow(/oversized/);expect(probe.readBytes).toBe(0);expect(probe.wholeReads).toBe(0);
  await writeFile(path.join(root,"Cargo.toml"),"é".repeat(MAX_NATIVE_INPUT_BYTES/2+1));await expect(inspectNativeProviderInputs(root)).rejects.toThrow(/oversized/);expect(probe.readBytes).toBe(0);
 });
 it("bounds actual growth during a retained descriptor read",async()=>{
  probe.beforeRead=()=>appendFile(path.join(root,"Cargo.toml"),"x".repeat(MAX_NATIVE_INPUT_BYTES+1));
  await expect(inspectNativeProviderInputs(root)).rejects.toThrow(/oversized/);expect(probe.readBytes).toBeLessThanOrEqual(MAX_NATIVE_INPUT_BYTES+1);expect(probe.wholeReads).toBe(0);
 });
 it("refuses actual path replacement while preserving original and replacement bytes",async()=>{
  probe.beforeRead=async()=>{await rename(path.join(root,"Cargo.toml"),path.join(root,"retained.toml"));await writeFile(path.join(root,"Cargo.toml"),cargo);};
  await expect(inspectNativeProviderInputs(root)).rejects.toThrow(/changed native input/);expect(await readFile(path.join(root,"retained.toml"),"utf8")).toBe(cargo);expect(await readFile(path.join(root,"Cargo.toml"),"utf8")).toBe(cargo);
 });
 it("rejects non-UTF8 and multiply linked native manifests",async()=>{
  await writeFile(path.join(root,"Cargo.toml"),Buffer.from([255]));await expect(inspectNativeProviderInputs(root)).rejects.toThrow(/invalid UTF-8/);
  await writeFile(path.join(root,"Cargo.toml"),cargo);await link(path.join(root,"Cargo.toml"),path.join(root,"alias.toml"));probe.readBytes=0;await expect(inspectNativeProviderInputs(root)).rejects.toThrow(/unsafe native input/);expect(probe.readBytes).toBe(0);
 });
 it("refuses a linked config ancestor without touching its owned sentinel",async()=>{
  const outside=path.join(root,"other");await mkdir(outside);await writeFile(path.join(outside,"config.toml"),"keep");await symlink(outside,path.join(root,".cargo"),process.platform==="win32"?"junction":"dir");
  await expect(inspectNativeProviderInputs(root)).rejects.toThrow(/unsafe native input/);expect(await readFile(path.join(outside,"config.toml"),"utf8")).toBe("keep");
 });
 it("binds Go command metadata and refuses linked command children",async()=>{
  await rm(path.join(root,"Cargo.toml"));await writeFile(path.join(root,"go.mod"),"module fixture\n\ngo 1.21\n");const first=await inspectNativeProviderInputs(root);await mkdir(path.join(root,"cmd"));await mkdir(path.join(root,"cmd","server"));const second=await inspectNativeProviderInputs(root);expect(first?.sha256).not.toBe(second?.sha256);
  await symlink(path.join(root,"missing"),path.join(root,"cmd","unsafe"),process.platform==="win32"?"junction":"dir");await expect(inspectNativeProviderInputs(root)).rejects.toThrow(/unsafe native input/);
 });
});
