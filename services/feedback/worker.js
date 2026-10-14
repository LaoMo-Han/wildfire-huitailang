import adminHtml from './admin.html';

const encoder = new TextEncoder();
const statusNames = ['open','in_progress','fixed'];
const json = (body,status=200) => new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'}});
const fail = (message,status=400) => { throw Object.assign(new Error(message),{status}); };
const digest = async value => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',encoder.encode(value))),b=>b.toString(16).padStart(2,'0')).join('');

async function limitedBody(request,max) {
  if(Number(request.headers.get('Content-Length'))>max) fail('内容太大',413);
  const reader=request.body?.getReader();
  if(!reader) return new Uint8Array();
  const chunks=[];let size=0;
  while(true){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>max){await reader.cancel();fail('内容太大',413);}chunks.push(value);}
  const buffer=new Uint8Array(size);let offset=0;for(const c of chunks){buffer.set(c,offset);offset+=c.length;}return buffer;
}
async function objectBody(request){
  try{
    const value=JSON.parse(new TextDecoder().decode(await limitedBody(request,1024)));
    if(!value||typeof value!=='object'||Array.isArray(value))fail('请求格式不正确');
    return value;
  }catch(error){if(error.status)throw error;fail('请求格式不正确');}
}
async function rate(request,env,action,limit) {
  const ip=request.headers.get('CF-Connecting-IP')||'unknown';
  const key=await digest(env.SESSION_SECRET+':'+action+':'+ip);
  const bucket=Math.floor(Date.now()/60000);
  const rows=await env.DB.batch([
    env.DB.prepare('DELETE FROM rate_limit WHERE bucket<?').bind(bucket-60),
    env.DB.prepare('INSERT INTO rate_limit(key,bucket,count) VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN bucket=excluded.bucket THEN count+1 ELSE 1 END,bucket=excluded.bucket RETURNING count').bind(key,bucket)
  ]);
  const result=rows[1].results[0];
  if(result.count>limit) fail('操作过于频繁，请稍后再试',429);
}
async function hmac(env,text){
  const key=await crypto.subtle.importKey('raw',encoder.encode(env.SESSION_SECRET),{name:'HMAC',hash:'SHA-256'},false,['sign','verify']);
  return {key,signature:new Uint8Array(await crypto.subtle.sign('HMAC',key,encoder.encode(text)))};
}
function b64(bytes){return btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');}
function unb64(text){const s=text.replaceAll('-','+').replaceAll('_','/');return Uint8Array.from(atob(s),c=>c.charCodeAt(0));}
async function admin(request,env){
  try{
    const value=(request.headers.get('Cookie')||'').split(';').map(s=>s.trim()).find(s=>s.startsWith('wf_admin='))?.slice(9);
    if(!value)return false;
    const [expiration,nonce,signature]=value.split('.');
    if(Number(expiration)<Date.now()||Number(expiration)>Date.now()+13*3600000)return false;
    const {key}=await hmac(env,expiration+'.'+nonce);
    return await crypto.subtle.verify('HMAC',key,unb64(signature),encoder.encode(expiration+'.'+nonce));
  }catch{return false;}
}
async function listing(env,url,isAdmin=false){
  const before=Number(url.searchParams.get('cursor'))||Number.MAX_SAFE_INTEGER;
  const status=url.searchParams.get('status');
  let sql='SELECT id,description,version,status,fixed_version,hidden,created_at FROM feedback WHERE id<?';
  const args=[before];if(!isAdmin)sql+=' AND hidden=0';
  if(statusNames.includes(status)){sql+=' AND status=?';args.push(status);}
  sql+=' ORDER BY id DESC LIMIT 21';
  const {results}=await env.DB.prepare(sql).bind(...args).all();
  const more=results.length>20;const items=results.slice(0,20);
  if(items.length){const {results:images}=await env.DB.prepare('SELECT id,feedback_id FROM images WHERE feedback_id IN ('+items.map(()=>'?').join(',')+')').bind(...items.map(f=>f.id)).all();for(const item of items)item.images=images.filter(i=>i.feedback_id===item.id).map(i=>i.id);}
  return json({items,next_cursor:more?items[items.length-1].id:null});
}
async function submit(request,env){
  await rate(request,env,'feedback',3);
  if(!request.headers.get('Content-Type')?.startsWith('multipart/form-data;'))fail('提交格式不正确');
  const buffer=await limitedBody(request,1650000);
  const form=await new Response(buffer,{headers:{'Content-Type':request.headers.get('Content-Type')||''}}).formData();
  const description=String(form.get('description')||'').trim();
  const version=String(form.get('version')||'').trim();
  if(description.length<3||description.length>4000)fail('请填写 3–4000 字的问题描述');
  if(version.length>60)fail('版本号过长');
  const token=String(form.get('turnstileToken')||'');
  if(!token||token.length>2048)fail('请完成验证',403);
  const verify=await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify',{method:'POST',body:new URLSearchParams({secret:env.TURNSTILE_SECRET,response:token,remoteip:request.headers.get('CF-Connecting-IP')||''}),signal:AbortSignal.timeout(10000)});
  if(!verify.ok)fail('验证暂时不可用，请重试',503);
  const result=await verify.json();
  if(result.success!==true||result.action!=='feedback'||result.hostname!=='laomo-han.github.io')fail('验证未通过，请重试',403);
  const files=form.getAll('images');if(files.length>3)fail('最多上传三张截图');
  const images=[];
  for(const file of files){
    if(typeof file==='string'||file.size<12||file.size>524288)fail('每张截图需小于 512 KiB');
    const bytes=new Uint8Array(await file.arrayBuffer());let mime='';
    if(bytes[0]===255&&bytes[1]===216&&bytes[2]===255)mime='image/jpeg';
    else if(bytes.slice(0,8).join(',')==='137,80,78,71,13,10,26,10')mime='image/png';
    else if(new TextDecoder().decode(bytes.slice(0,4))==='RIFF'&&new TextDecoder().decode(bytes.slice(8,12))==='WEBP')mime='image/webp';
    if(!mime||mime!==file.type)fail('仅支持 JPG、PNG、WebP 图片');
    images.push({id:crypto.randomUUID(),mime,data:bytes.buffer});
  }
  // UUID links every image to its report inside a single atomic batch.
  const marker=crypto.randomUUID();
  const batch=[env.DB.prepare('INSERT INTO feedback(description,version,created_at,submission_id) VALUES(?,?,?,?) RETURNING id').bind(description,version,Date.now(),marker)];
  for(const image of images)batch.push(env.DB.prepare('INSERT INTO images(id,feedback_id,mime,data) VALUES(?,(SELECT id FROM feedback WHERE submission_id=?),?,?)').bind(image.id,marker,image.mime,image.data));
  if(images.length){const bytes=images.reduce((n,i)=>n+i.data.byteLength,0);batch.push(env.DB.prepare('UPDATE storage SET bytes=CASE WHEN bytes+?>419430400 THEN NULL ELSE bytes+? END WHERE id=1').bind(bytes,bytes));}
  try{const response=await env.DB.batch(batch);return json({id:response[0].results[0].id},201);}
  catch(error){if(String(error).includes('NOT NULL constraint failed: storage.bytes'))fail('截图存储已满，请仅提交文字',507);throw error;}
}
async function route(request,env){
  const url=new URL(request.url);const path=url.pathname;
  if(path==='/health')return json({ok:true});
  if(path==='/admin')return new Response(adminHtml,{headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','X-Frame-Options':'DENY'}});
  if(path==='/api/admin/login'&&request.method==='POST'){
    if(request.headers.get('Origin')!==url.origin)fail('请求来源不正确',403);
    await rate(request,env,'login',5);
    const input=await objectBody(request);
    const actual=encoder.encode(await digest(String(input.password||'')));
    const expected=encoder.encode(env.ADMIN_HASH);
    if(actual.length!==expected.length||!crypto.subtle.timingSafeEqual(actual,expected))fail('管理口令错误',401);
    const text=(Date.now()+12*3600000)+'.'+crypto.randomUUID();const {signature}=await hmac(env,text);
    const response=json({ok:true});response.headers.set('Set-Cookie','wf_admin='+text+'.'+b64(signature)+'; HttpOnly; Secure; SameSite=Strict; Path=/api/admin; Max-Age=43200');return response;
  }
  if(path.startsWith('/api/admin/')){
    if(!await admin(request,env))fail('需要管理口令',401);
    if(request.method!=='GET'&&request.headers.get('Origin')!==url.origin)fail('请求来源不正确',403);
    if(path==='/api/admin/logout'&&request.method==='POST'){const response=json({ok:true});response.headers.set('Set-Cookie','wf_admin=; HttpOnly; Secure; SameSite=Strict; Path=/api/admin; Max-Age=0');return response;}
    if(path==='/api/admin/feedback'&&request.method==='GET')return listing(env,url,true);
    const imageMatch=path.match(/^\/api\/admin\/images\/([a-f0-9-]{36})$/);
    if(imageMatch&&request.method==='GET'){
      const image=await env.DB.prepare('SELECT mime,data FROM images WHERE id=?').bind(imageMatch[1]).first();
      if(!image)fail('图片不存在',404);
      return new Response(Uint8Array.from(image.data),{headers:{'Content-Type':image.mime,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
    }
    const match=path.match(/^\/api\/admin\/feedback\/(\d+)$/);
    if(match&&request.method==='PATCH'){
      const input=await objectBody(request);
      if(!statusNames.includes(input.status)||typeof input.hidden!=='boolean'||String(input.fixed_version||'').length>60)fail('状态无效');
      await env.DB.prepare('UPDATE feedback SET status=?,hidden=?,fixed_version=? WHERE id=?').bind(input.status,input.hidden?1:0,String(input.fixed_version||''),Number(match[1])).run();return json({ok:true});
    }
  }
  if(path==='/api/feedback'&&request.method==='GET')return listing(env,url);
  if(path==='/api/feedback'&&request.method==='POST'){
    if(request.headers.get('Origin')!==env.PUBLIC_ORIGIN)fail('请求来源不正确',403);
    return submit(request,env);
  }
  const match=path.match(/^\/api\/images\/([a-f0-9-]{36})$/);
  if(match&&request.method==='GET'){
    const image=await env.DB.prepare('SELECT i.mime,i.data FROM images i JOIN feedback f ON f.id=i.feedback_id WHERE i.id=? AND f.hidden=0').bind(match[1]).first();
    if(!image)fail('图片不存在',404);
    return new Response(Uint8Array.from(image.data),{headers:{'Content-Type':image.mime,'Cache-Control':'no-store','Content-Security-Policy':"default-src 'none'",'X-Content-Type-Options':'nosniff'}});
  }
  fail('页面不存在',404);
}
export default {async fetch(request,env){
  const origin=request.headers.get('Origin');
  let response;
  try{response=request.method==='OPTIONS'?new Response(null,{status:204}):await route(request,env);}
  catch(error){const status=error.status||503;if(!error.status)console.error(JSON.stringify({event:'request_failed',message:String(error).slice(0,200)}));response=json({error:error.status?error.message:'服务暂时不可用，请稍后重试'},status);}
  response.headers.set('X-Content-Type-Options','nosniff');
  if(origin===env.PUBLIC_ORIGIN){response.headers.set('Access-Control-Allow-Origin',origin);response.headers.set('Vary','Origin');response.headers.set('Access-Control-Allow-Methods','GET, POST, OPTIONS');response.headers.set('Access-Control-Allow-Headers','Content-Type');}
  return response;
}};
