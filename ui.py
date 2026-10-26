"""Local web UI for the invoice intake demo. Standard library only; binds to localhost.

    python ui.py            # then open http://127.0.0.1:8765
"""
import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from intake.extract import FIELDS, extract
from intake.generate import APPROVED_VENDORS, generate
from intake.pipeline import process_dir
from intake.validate import validate

HOST, PORT = "127.0.0.1", 8765
ROOT = Path(__file__).parent
OUT = ROOT / "output"
LOCK = threading.Lock()
STATE = {"seen": set(), "docs": {}}

SAMPLE = """INVOICE
Vendor: Acme Supplies Ltd
Phone: 555-0100
Invoice No: INV-2041
Date: 2025-03-14
Due: 2025-04-13

4 x Paper A4 @ 12.50
2 x Toner cartridge @ 89.00

Subtotal: 228.00
Tax (21%): 47.88
Total Due: 275.88 EUR
"""


def analyse(text, seen):
    fields = extract(text)
    reasons = validate(fields, APPROVED_VENDORS, seen)
    return {
        "fields": {f: fields[f][0] for f in FIELDS},
        "confidence": {f: fields[f][1] for f in FIELDS},
        "reasons": reasons,
        "decision": "review" if reasons else "auto_approved",
    }


def run_batch(n, seed):
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "in"
        generate(data, n=n, seed=seed)
        results = process_dir(data, Path(tmp) / "out")
        docs = {}
        for r in results:
            r["text"] = (data / r["file"]).read_text(encoding="utf-8")
            r["reviewer"] = None
            docs[r["file"]] = r
    return docs


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE.replace("__SAMPLE__", json.dumps(SAMPLE)), "text/html")
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        try:
            body = self._json()
            with LOCK:
                if self.path == "/api/process":
                    text = str(body.get("text", ""))[:20000]
                    self._send(200, json.dumps(analyse(text, STATE["seen"])))
                elif self.path == "/api/reset":
                    STATE["seen"].clear()
                    self._send(200, json.dumps({"ok": True}))
                elif self.path == "/api/batch":
                    n = max(5, min(int(body.get("n", 40)), 300))
                    STATE["docs"] = run_batch(n, int(body.get("seed", 7)))
                    self._send(200, json.dumps(list(STATE["docs"].values())))
                elif self.path == "/api/review":
                    doc = STATE["docs"].get(body.get("file"))
                    action = body.get("action")
                    if doc is None or action not in ("approved", "rejected"):
                        self._send(400, json.dumps({"error": "bad request"}))
                        return
                    doc["reviewer"] = action
                    OUT.mkdir(exist_ok=True)
                    with open(OUT / "reviewer_decisions.jsonl", "a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"file": doc["file"], "action": action,
                                             "reasons": doc["reasons"]}) + "\n")
                    self._send(200, json.dumps({"ok": True}))
                else:
                    self._send(404, json.dumps({"error": "not found"}))
        except (ValueError, KeyError) as exc:
            self._send(400, json.dumps({"error": str(exc)}))


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Invoice Intake</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--text:#1b1f24;--muted:#5f6b7a;--line:#dde1e6;--ok:#157f3b;--okbg:#e3f4e8;--warn:#a15c00;--warnbg:#fff1d6;--bad:#b3261e;--badbg:#fde7e5;--accent:#1f5fbf}
@media (prefers-color-scheme:dark){:root{--bg:#14171a;--card:#1d2126;--text:#e8eaed;--muted:#98a2b0;--line:#2f353c;--ok:#5fd187;--okbg:#17321f;--warn:#f0b455;--warnbg:#3a2c10;--bad:#ff8a80;--badbg:#3d1b18;--accent:#7aa8f0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:20px 16px 48px}h1{font-size:22px;margin:0 0 4px}.sub{color:var(--muted);margin:0 0 16px}
.tabs{display:flex;gap:6px;margin-bottom:14px}.tab{padding:8px 14px;border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:8px;cursor:pointer;font:inherit}
.tab.on{border-color:var(--accent);color:var(--accent);font-weight:600}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:800px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
textarea{width:100%;min-height:300px;font:13px/1.45 ui-monospace,Consolas,monospace;background:var(--bg);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:10px;resize:vertical}
button.btn{padding:8px 14px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--text);cursor:pointer;font:inherit}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}button.btn:disabled{opacity:.5;cursor:default}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;align-items:center}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);font-size:14px}th{color:var(--muted);font-weight:600}
.bar{height:6px;border-radius:3px;background:var(--line);width:70px;display:inline-block;vertical-align:middle;overflow:hidden}.bar i{display:block;height:100%}
.badge{display:inline-block;padding:3px 10px;border-radius:999px;font-weight:600;font-size:13px}
.auto{background:var(--okbg);color:var(--ok)}.review{background:var(--warnbg);color:var(--warn)}.rej{background:var(--badbg);color:var(--bad)}
.reason{display:inline-block;margin:2px 4px 2px 0;padding:2px 8px;border-radius:6px;background:var(--badbg);color:var(--bad);font-size:12px;font-family:ui-monospace,Consolas,monospace}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}.stat{flex:1;min-width:130px}.stat b{font-size:24px;display:block}
.list{max-height:520px;overflow:auto}.item{padding:8px 10px;border-bottom:1px solid var(--line);cursor:pointer;display:flex;justify-content:space-between;gap:8px;align-items:center}
.item.sel{background:var(--bg)}.muted{color:var(--muted)}pre{white-space:pre-wrap;font:12.5px/1.45 ui-monospace,Consolas,monospace;background:var(--bg);padding:10px;border-radius:8px;border:1px solid var(--line);max-height:220px;overflow:auto;margin:0 0 10px}
.note{font-size:13px;color:var(--muted);margin-top:12px}
</style></head><body><main>
<h1>Invoice Intake</h1>
<p class="sub">Extract, validate, then auto-approve or send to a human with the reason. Demo on synthetic data.</p>
<div class="tabs"><button class="tab on" id="t1">Single invoice</button><button class="tab" id="t2">Batch demo</button></div>

<section id="p1"><div class="grid">
<div class="card"><label for="txt"><b>Invoice text</b></label>
<textarea id="txt" spellcheck="false"></textarea>
<div class="row"><button class="btn primary" id="go">Process</button><button class="btn" id="sample">Load sample</button>
<label class="btn" for="file">Open .txt file</label><input id="file" type="file" accept=".txt,text/plain" hidden>
<button class="btn" id="reset" title="Forget invoices seen so far (duplicate check)">Reset duplicates</button></div>
<p class="note">Try editing the total, changing the vendor, or deleting the invoice number. Submitting the same invoice twice triggers DUPLICATE.</p></div>
<div class="card" id="out"><p class="muted">Result appears here.</p></div></div></section>

<section id="p2" hidden>
<div class="row" style="margin:0 0 12px"><label>Invoices <input id="n" type="number" value="40" min="5" max="300" style="width:80px"></label>
<label>Seed <input id="seed" type="number" value="7" style="width:70px"></label><button class="btn primary" id="gen">Generate &amp; process</button></div>
<div class="stats" id="stats"></div>
<div class="grid"><div class="card"><div class="row" style="margin:0 0 8px"><button class="btn" data-f="all">All</button><button class="btn" data-f="review">Needs review</button><button class="btn" data-f="auto_approved">Auto-approved</button></div><div class="list" id="list"><p class="muted">Click Generate &amp; process.</p></div></div>
<div class="card" id="detail"><p class="muted">Select an invoice.</p></div></div></section>
</main>
<script>
const $=id=>document.getElementById(id);
const SAMPLE=__SAMPLE__;
const post=(u,b)=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})}).then(r=>r.json());
const el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!==undefined)e.textContent=x;return e};
const LABELS={vendor:'Vendor',invoice_number:'Invoice no.',invoice_date:'Invoice date',due_date:'Due date',currency:'Currency',subtotal:'Subtotal',tax:'Tax',total:'Total'};
function show(tab){$('p1').hidden=tab!==1;$('p2').hidden=tab!==2;$('t1').classList.toggle('on',tab===1);$('t2').classList.toggle('on',tab===2)}
$('t1').onclick=()=>show(1);$('t2').onclick=()=>show(2);

function badge(r,reviewer){
  if(reviewer)return el('span','badge '+(reviewer==='approved'?'auto':'rej'),'Reviewer: '+reviewer);
  return el('span','badge '+(r.decision==='review'?'review':'auto'),r.decision==='review'?'Needs review':'Auto-approved')}
function render(target,r,reviewer){
  target.replaceChildren();
  const h=el('div','row');h.style.marginTop='0';h.append(badge(r,reviewer));target.append(h);
  const rs=el('div');rs.style.margin='8px 0';
  if(r.reasons.length)r.reasons.forEach(x=>rs.append(el('span','reason',x)));else rs.append(el('span','muted','All checks passed.'));
  target.append(rs);
  const t=el('table');const hd=el('tr');['Field','Value','Confidence'].forEach(x=>hd.append(el('th',null,x)));t.append(hd);
  Object.keys(LABELS).forEach(k=>{
    const tr=el('tr');tr.append(el('td',null,LABELS[k]));
    const v=r.fields[k];tr.append(el('td',v===null?'muted':null,v===null?'not found':v));
    const c=r.confidence[k];const td=el('td');const bar=el('span','bar');const i=el('i');
    i.style.width=(c*100)+'%';i.style.background=c>=0.8?'var(--ok)':c>0?'var(--warn)':'var(--bad)';bar.append(i);
    td.append(bar,document.createTextNode(' '+c.toFixed(2)));tr.append(td);t.append(tr)});
  target.append(t)}

$('txt').value=SAMPLE;
$('sample').onclick=()=>{$('txt').value=SAMPLE};
$('file').onchange=e=>{const f=e.target.files[0];if(f)f.text().then(x=>{$('txt').value=x})};
$('go').onclick=async()=>{$('go').disabled=true;try{render($('out'),await post('/api/process',{text:$('txt').value}))}finally{$('go').disabled=false}};
$('reset').onclick=async()=>{await post('/api/reset');$('out').replaceChildren(el('p','muted','Duplicate memory cleared.'))};

let docs=[],filter='all',sel=null;
$('gen').onclick=async()=>{$('gen').disabled=true;try{docs=await post('/api/batch',{n:+$('n').value,seed:+$('seed').value});sel=null;draw()}finally{$('gen').disabled=false}};
document.querySelectorAll('[data-f]').forEach(b=>b.onclick=()=>{filter=b.dataset.f;draw()});
function draw(){
  const rev=docs.filter(d=>d.decision==='review').length;
  const st=$('stats');st.replaceChildren();
  [['Total',docs.length],['Auto-approved',docs.length-rev],['Needs review',rev],['Reviewed',docs.filter(d=>d.reviewer).length]].forEach(([k,v])=>{
    const c=el('div','card stat');c.append(el('b',null,v),el('span','muted',k));st.append(c)});
  const list=$('list');list.replaceChildren();
  docs.filter(d=>filter==='all'||d.decision===filter).forEach(d=>{
    const it=el('div','item'+(sel&&sel.file===d.file?' sel':''));
    const left=el('div');left.append(el('div',null,d.file+'  '+(d.fields.vendor||'(no vendor)')),el('div','muted',(d.fields.total||'?')+'  '+(d.reasons[0]||'')));
    it.append(left,badge(d,d.reviewer));it.onclick=()=>{sel=d;draw()};list.append(it)});
  const det=$('detail');det.replaceChildren();
  if(!sel){det.append(el('p','muted','Select an invoice.'));return}
  det.append(el('b',null,sel.file),el('pre',null,sel.text));
  const box=el('div');det.append(box);render(box,sel,sel.reviewer);
  if(sel.decision==='review'&&!sel.reviewer){
    const row=el('div','row');
    [['approved','Approve'],['rejected','Reject']].forEach(([a,l])=>{const b=el('button','btn'+(a==='approved'?' primary':''),l);
      b.onclick=async()=>{await post('/api/review',{file:sel.file,action:a});sel.reviewer=a;draw()};row.append(b)});
    det.append(row)}}
</script></body></html>"""


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Invoice Intake UI on http://{HOST}:{PORT}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
