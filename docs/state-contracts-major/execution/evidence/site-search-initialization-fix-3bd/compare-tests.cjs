const fs=require('node:fs'),crypto=require('node:crypto');
const ts=require('C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter/site/node_modules/typescript');
const before='C:/Users/brenn/AppData/Local/Temp/ca-s55-interactions-3bd/site/test/components/search-interactions.spec.ts';
const after=__dirname+'/site/test/components/search-interactions.spec.ts';
function tests(file){const text=fs.readFileSync(file,'utf8');const tree=ts.createSourceFile(file,text,ts.ScriptTarget.Latest,true);const results={};function visit(node){if(ts.isCallExpression(node)&&node.expression.getText(tree)==='test'&&ts.isStringLiteral(node.arguments[0]))results[node.arguments[0].text]=node.getText(tree);ts.forEachChild(node,visit);}visit(tree);return results;}
const old=tests(before),current=tests(after);const checks=[];
for(const [name,text] of Object.entries(old)){if(current[name]!==text)throw Error('Original assertion changed: '+name);checks.push({name,exact_call_expression_unchanged:true,sha256:crypto.createHash('sha256').update(text).digest('hex')});}
if(checks.length!==5||Object.keys(current).length!==6)throw Error('Unexpected test inventory');
fs.writeFileSync(__dirname+'/regression-identity.json',JSON.stringify({original_five_test_calls:checks,added_case:Object.keys(current).filter(n=>!(n in old)),scope:'Original5 test call expressions are byte-identical. Fixture helper adds reject mode and preserves counters across cache-busted import; no original assertion modified.'},null,2)+'\n');
console.log('Original5 exact test calls unchanged; one options rejection control added.');
