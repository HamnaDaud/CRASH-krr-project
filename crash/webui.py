"""Web UI for CRASH: a single HTML page (no external assets) plus a small JSON API.
GET /            the page
GET /api/ask?q=  JSON: status, answer, sparql, columns, rows (with stored/inferred tags), grounding, attempts
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from .answer import ask_grounded
from .llm import PendingResponse

EXAMPLES = [
    "Which five local authorities had the most fatal or serious collisions on A roads in wet or icy conditions?",
    "Which collisions involved a vulnerable road user, and what types of vehicle were involved? Give the number of such collisions and the most common vehicle types with counts.",
    "Which areas (LSOAs) are high-risk, meaning at least three serious or fatal collisions, and which police force covers each one?",
    "For collision 202560C002220, what are its vehicles, casualties, severity, road and weather conditions and administrative areas?",
    "Was alcohol or driver fatigue the cause of collision 202560C002220?",
    "/similar Collision_202560C013816",
]

PAGE = r"""<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>CRASH road-safety advisor</title>
<style>
:root{--bg:#f4f6fb;--card:#fff;--ink:#0f172a;--mute:#64748b;--line:#e2e8f0;--brand:#1d4ed8;--brand2:#0ea5e9;
--stored:#16a34a;--inferred:#2563eb;--pred:#a21caf;--warn:#b45309;--bad:#b91c1c}
@media(prefers-color-scheme:dark){:root{--bg:#0b1120;--card:#111a2e;--ink:#e6edf7;--mute:#93a4bd;--line:#223049;--brand:#60a5fa;--brand2:#38bdf8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{background:linear-gradient(120deg,#1e3a8a,#0369a1);color:#fff;padding:28px 16px 64px}
.wrap{max-width:980px;margin:0 auto;padding:0 16px}header .wrap{padding:0}
h1{margin:0;font-size:28px;letter-spacing:.5px}h1 span{opacity:.75;font-weight:400;font-size:16px;margin-left:8px}
header p{margin:6px 0 0;opacity:.9}
.search{margin-top:-40px;background:var(--card);border-radius:14px;box-shadow:0 8px 30px rgba(15,23,42,.15);padding:14px;display:flex;gap:10px}
.search input{flex:1;font:inherit;padding:12px 14px;border:1px solid var(--line);border-radius:10px;background:transparent;color:var(--ink);min-width:0}
.search input:focus{outline:2px solid var(--brand);border-color:transparent}
button{font:inherit;border:0;border-radius:10px;padding:0 22px;background:linear-gradient(120deg,var(--brand),var(--brand2));color:#fff;font-weight:600;cursor:pointer}
button:disabled{opacity:.6;cursor:wait}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}
.chip{border:1px solid var(--line);background:var(--card);color:var(--ink);padding:6px 12px;border-radius:999px;font-size:13px;cursor:pointer}
.chip:hover{border-color:var(--brand);color:var(--brand)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin:14px 0}
.card h3{margin:0 0 10px;font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--mute)}
.q{font-weight:600;font-size:17px}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;color:#fff;vertical-align:middle}
.b-answered{background:var(--stored)}.b-insufficient_evidence{background:var(--warn)}.b-error{background:var(--bad)}
.tag{display:inline-block;padding:1px 8px;border-radius:6px;font-size:12px;font-weight:600;color:#fff}
.t-stored{background:var(--stored)}.t-inferred{background:var(--inferred)}.t-predicted{background:var(--pred)}
.ans{white-space:normal}.ans table{border-collapse:collapse;margin:8px 0}.ans td,.ans th{border:1px solid var(--line);padding:4px 10px}
.ans ul{padding-left:20px;margin:6px 0}.ai{font-size:12px;color:var(--mute);margin-top:10px}
.tw{overflow:auto;max-height:340px;border:1px solid var(--line);border-radius:10px}
table.ev{border-collapse:collapse;width:100%;font-size:13px}table.ev th{position:sticky;top:0;background:var(--bg);text-align:left}
table.ev td:nth-child(-n+2),.tag{white-space:nowrap}table.ev td,table.ev th{padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:top;max-width:340px;overflow-wrap:anywhere}
details summary{cursor:pointer;color:var(--brand);font-weight:600}pre{background:var(--bg);padding:12px;border-radius:10px;overflow:auto;font-size:12.5px}
.warn{background:rgba(180,83,9,.12);border-left:4px solid var(--warn);padding:8px 12px;border-radius:6px;margin-top:10px}
.spin{display:none;text-align:center;padding:24px;color:var(--mute)}.spin i{display:inline-block;width:22px;height:22px;border:3px solid var(--line);
border-top-color:var(--brand);border-radius:50%;animation:s 1s linear infinite;vertical-align:middle;margin-right:10px}@keyframes s{to{transform:rotate(360deg)}}
.legend{font-size:13px;color:var(--mute);margin:24px 0 40px}.meta{font-size:12px;color:var(--mute);margin-left:8px}
@media(max-width:600px){.search{flex-direction:column}button{padding:12px}}
</style>
<header><div class=wrap><h1>CRASH<span>Collision Risk Analysis through Semantic Hierarchies</span></h1>
<p>Knowledge-grounded road-safety advisor for Great Britain · STATS19 2025 · North Wales &amp; Gwent</p></div></header>
<div class=wrap>
<form class=search id=f><input id=q autofocus placeholder="Ask about collisions, areas, road conditions and road users..."><button id=go>Ask</button></form>
<div class=chips id=chips></div>
<div class=spin id=spin><i></i>Planning the query, running it on the graph and writing the answer (5-30 s)...</div>
<div id=out></div>
<div class=legend><span class="tag t-stored">stored</span> fact in the graph &nbsp; <span class="tag t-inferred">inferred</span> derived by rules R1-R8 &nbsp;
<span class="tag t-predicted">predicted</span> TransE prediction, not a fact &nbsp; · AI-written text is checked against the retrieved rows.</div></div>
<script>
const EX=__EXAMPLES__;const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
EX.forEach(t=>{const b=document.createElement('button');b.type='button';b.className='chip';b.textContent=t.length>62?t.slice(0,60)+'…':t;b.title=t;
b.onclick=()=>{$('q').value=t;ask(t)};$('chips').appendChild(b)});
function md(t){let h=esc(t).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').split('\n'),o='',inl=false,tb=false;
for(let l of h){const li=l.match(/^\s*[-*]\s+(.*)/);const tr=l.match(/^\s*\|(.+)\|\s*$/);
if(li){if(!inl){o+='<ul>';inl=true}o+='<li>'+li[1]+'</li>';continue}if(inl){o+='</ul>';inl=false}
if(tr){if(/^[\s|:-]+$/.test(l))continue;if(!tb){o+='<table>';tb=true}o+='<tr>'+tr[1].split('|').map(c=>'<td>'+c.trim()+'</td>').join('')+'</tr>';continue}
if(tb){o+='</table>';tb=false}o+=l.trim()?'<p>'+l+'</p>':''}
return o+(inl?'</ul>':'')+(tb?'</table>':'')}
function card(title,body){return '<div class=card><h3>'+title+'</h3>'+body+'</div>'}
function show(r,q){let h=card('Question','<div class=q>'+esc(q)+'</div>');
if(r.error){$('out').innerHTML=h+card('Error','<span class="badge b-error">error</span> '+esc(r.error));return}
if(r.kind==='similar'){h+=card('Predicted-similar collisions <span class=meta>from TransE, restricted to the rule-certified pool</span>',
'<div class=tw><table class=ev><tr><th>collision</th><th>cosine</th><th>label</th><th>rule guarantee</th><th>shared attributes</th></tr>'+
r.neighbours.map(n=>'<tr><td>'+esc(n.collision)+'</td><td>'+n.cosine+'</td><td><span class="tag t-predicted">predicted</span></td><td>'+esc(n.rule_guarantee)+
'</td><td>'+esc(Object.entries(n.shared_attributes).map(([k,v])=>k+'='+v).join('; '))+'</td></tr>').join('')+'</table></div>');
$('out').innerHTML=h;return}
h+=card('Answer <span class="badge b-'+r.status+'">'+r.status.replace('_',' ')+'</span><span class=meta>'+(r.attempts>1?r.attempts+' query attempts':'')+'</span>',
'<div class=ans>'+md(r.answer)+'</div><div class=ai>AI-written text. Every statement should cite collision IDs and a tag.</div>'+
(r.grounding&&(r.grounding.unsupported_ids.length||r.grounding.unsupported_numbers.length)?
'<div class=warn><b>Grounding check:</b> not found in the retrieved rows → '+esc(JSON.stringify(r.grounding))+'</div>':''));
if(r.rows&&r.rows.length){const cols=r.columns.filter(c=>c!=='evidence').concat(r.columns.includes('evidence')?['evidence']:[]);
h+=card('Evidence from the knowledge graph <span class=meta>'+r.rows.length+' rows (first 25 shown)</span>','<div class=tw><table class=ev><tr><th>tag</th>'+
cols.map(c=>'<th>'+esc(c)+'</th>').join('')+'</tr>'+r.rows.slice(0,25).map(x=>'<tr><td><span class="tag t-'+x.tag+'">'+x.tag+'</span></td>'+
cols.map(c=>{let v=x.row[c]||'';if(v.length>140)v=v.slice(0,140)+'…';return '<td>'+esc(v)+'</td>'}).join('')+'</tr>').join('')+'</table></div>')}
if(r.extra&&r.extra.rows.length)h+=card('Overall figure <span class=meta>second query</span>','<div class=tw><table class=ev><tr><th>tag</th>'+r.extra.columns.map(c=>'<th>'+esc(c)+'</th>').join('')+'</tr>'+r.extra.rows.map(x=>'<tr><td><span class="tag t-'+x.tag+'">'+x.tag+'</span></td>'+r.extra.columns.map(c=>'<td>'+esc(x.row[c]||'')+'</td>').join('')+'</tr>').join('')+'</table></div>');
if(r.sparql)h+=card('How it was retrieved','<details><summary>Show the SPARQL written by the model</summary><pre>'+esc(r.sparql)+'</pre></details>');
$('out').innerHTML=h}
async function ask(q){q=q.trim();if(!q)return;$('go').disabled=true;$('spin').style.display='block';$('out').innerHTML='';
try{const r=await fetch('/api/ask?q='+encodeURIComponent(q));show(await r.json(),q)}catch(e){show({error:String(e)},q)}
$('go').disabled=false;$('spin').style.display='none'}
$('f').onsubmit=e=>{e.preventDefault();ask($('q').value)};
</script></html>"""


def answer_json(retr, llm, hy, q):
    if q.startswith("/similar"):
        cid = q.split()[1].replace("res:", "")
        d = hy.similar_collisions(cid)
        return {"kind": "similar", "neighbours": d["neighbours"]}
    res = ask_grounded(retr, llm, q)
    r = res["retrieval"]
    return {"kind": "answer", "status": res["status"], "answer": res["answer"], "sparql": r["sparql"], "columns": r["columns"],
            "rows": r["rows"][:25], "extra": r.get("extra"), "grounding": res.get("grounding"), "attempts": r.get("attempts", 1)}


def serve(port, retr, llm):
    from .hybrid import Hybrid
    hy = Hybrid(retr.kg)
    page = PAGE.replace("__EXAMPLES__", json.dumps(EXAMPLES)).encode()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/api/ask":
                q = parse_qs(u.query).get("q", [""])[0]
                try:
                    body = answer_json(retr, llm, hy, q)
                except PendingResponse as e:
                    body = {"error": f"LLM response pending (offline replay backend): {e}"}
                except Exception as e:
                    body = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
                data, ctype = json.dumps(body).encode(), "application/json"
            else:
                data, ctype = page, "text/html; charset=utf-8"
            self.send_response(200); self.send_header("Content-Type", ctype); self.end_headers()
            self.wfile.write(data)
    print(f"CRASH web UI on http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
