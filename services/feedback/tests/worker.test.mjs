// Test fixtures use SQLite and a fake Siteverify response. Production security
// bindings and deployed Turnstile verification are never changed by this test.
import {readFile,writeFile,mkdtemp} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {webcrypto,timingSafeEqual} from 'node:crypto';
import assert from 'node:assert/strict';
const here=dirname(fileURLToPath(import.meta.url));
const temp=await mkdtemp(join(tmpdir(),'wildfire-feedback-test-'));
const database=join(temp,'test.db');
function sql(commands=[],schema){
 const result=spawnSync('python',[join(here,'sqlite_bridge.py')],{input:JSON.stringify({database,commands,schema}),encoding:'utf8'});
 if(result.status!==0)throw Error(result.stderr);
 const rows=JSON.parse(result.stdout);if(rows.error)throw Error(rows.error);return rows;
}
sql([],join(here,'../schema.sql'));
class Statement {
 constructor(query,params=[]){this.sql=query;this.params=params;}
 bind(...params){return new Statement(this.sql,params.map(v=>v instanceof ArrayBuffer?{blob:[...new Uint8Array(v)]}:v));}
 async first(){return sql([this])[0].results[0]||null;}
 async all(){return sql([this])[0];}
 async run(){return sql([this])[0];}
}
Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
crypto.subtle.timingSafeEqual=(a,b)=>timingSafeEqual(Buffer.from(a),Buffer.from(b));
globalThis.fetch=async(url,options)=>{
 assert.equal(url,'https://challenges.cloudflare.com/turnstile/v0/siteverify');
 return new Response(JSON.stringify({success:options.body.get('response')==='fixture-valid',action:'feedback',hostname:'laomo-han.github.io'}));
};
const source=(await readFile(join(here,'../worker.js'),'utf8')).replace("import adminHtml from './admin.html';","const adminHtml = 'test admin';");
const module=join(temp,'worker.mjs');await writeFile(module,source);
const worker=(await import(pathToFileURL(module))).default;
const env={PUBLIC_ORIGIN:'https://laomo-han.github.io',SESSION_SECRET:'fixture-only',TURNSTILE_SECRET:'fixture-only',
 ADMIN_HASH:[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode('fixture-password')))].map(b=>b.toString(16).padStart(2,'0')).join(''),
 DB:{prepare:query=>new Statement(query),batch:async statements=>sql(statements)}};
const api='https://fixture.test';let counter=0;
const png=Buffer.from('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000b49444154789c636000020000050001a5f645400000000049454e44ae426082','hex');
function request(path,options={}){return worker.fetch(new Request(api+path,options),env);}
assert.equal((await request('/api/admin/login',{method:'POST',headers:{Origin:api},body:'invalid-json'})).status,400);
async function submit({images=[],origin=env.PUBLIC_ORIGIN,token='fixture-valid',ip}={}){
 const form=new FormData();form.set('description','anonymous test report');form.set('version','test.1');form.set('turnstileToken',token);
 for(const image of images)form.append('images',new Blob([image.bytes],{type:image.mime}),'test.png');
 return request('/api/feedback',{method:'POST',headers:{Origin:origin,'CF-Connecting-IP':ip||'fixture-'+counter++},body:form});
}
assert.equal((await submit({origin:'https://evil.test'})).status,403);
assert.equal((await submit({token:'invalid'})).status,403);
assert.equal((await submit({images:[{bytes:png,mime:'image/svg+xml'}]})).status,400);
assert.equal((await submit({images:Array.from({length:4},()=>({bytes:png,mime:'image/png'}))})).status,400);
assert.equal((await submit({images:[{bytes:Buffer.alloc(524289),mime:'image/png'}]})).status,400);
let result=await submit({images:[{bytes:png,mime:'image/png'}]});assert.equal(result.status,201);const id=(await result.json()).id;
let listing=await (await request('/api/feedback')).json();assert.equal(listing.items[0].id,id);
const imageId=listing.items[0].images[0];const image=await request('/api/images/'+imageId);assert.deepEqual(Buffer.from(await image.arrayBuffer()),png);
console.log('PASS anonymous submission, image BLOB, validation and public list');
for(let i=0;i<3;i++)assert.equal((await submit({ip:'limited'})).status,201);
assert.equal((await submit({ip:'limited'})).status,429);
console.log('PASS atomic submission rate limit');
const before=sql([{sql:'SELECT COUNT(*) AS count FROM feedback'}])[0].results[0].count;
sql([{sql:'UPDATE storage SET bytes=419430399 WHERE id=1'}]);
assert.equal((await submit({images:[{bytes:png,mime:'image/png'}]})).status,507);
assert.equal(sql([{sql:'SELECT COUNT(*) AS count FROM feedback'}])[0].results[0].count,before);
assert.equal((await submit()).status,201);
console.log('PASS image quota rolls back report and preserves text-only submissions');
result=await request('/api/admin/login',{method:'POST',headers:{Origin:api},body:JSON.stringify({password:'fixture-password'})});assert.equal(result.status,200);
const cookie=result.headers.get('Set-Cookie').split(';')[0];
assert.equal((await request('/api/admin/feedback/'+id,{method:'PATCH',headers:{Cookie:cookie,Origin:api},body:JSON.stringify({status:'fixed',hidden:true,fixed_version:'test.2'})})).status,200);
assert.equal((await request('/api/images/'+imageId)).status,404);
assert.equal((await request('/api/admin/images/'+imageId,{headers:{Cookie:cookie}})).status,200);
listing=await (await request('/api/feedback')).json();assert.ok(listing.items.every(row=>row.id!==id));
assert.equal((await request('/api/admin/feedback')).status,401);
assert.equal((await request('/api/admin/feedback/'+id,{method:'PATCH',headers:{Cookie:cookie,Origin:'https://evil.test'},body:'{}'})).status,403);
console.log('PASS admin session, CSRF, status and private hidden screenshots');
