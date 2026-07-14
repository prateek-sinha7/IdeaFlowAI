/* ============================================================
   Flowin Docs — shared app script (vanilla, no dependencies)
   Renders the sidebar nav, the interactive flow stepper, the
   capability/event/phase widgets, search + prev/next paging.
   Each page sets <body data-page="ID"> and may define:
     window.FLOW  = [{t,d,b?,bc?}, ...]   -> interactive stepper
     window.CAP   = [{k,n,ua,d}, ...]     -> capability catalog
     window.EV    = [{t,g,d}, ...]        -> event table
     window.PHASES= [[n,name,tag,desc]]   -> phase timeline
   ============================================================ */
(function(){
  "use strict";

  /* ---- single source of truth: navigation + page order ---- */
  var NAV = [
    {grp:"Start here", items:[
      {id:"index", t:"Home / Overview", ic:"\uD83E\uDDED"},
      {id:"getting-started", t:"Getting Started", ic:"\uD83D\uDE80"},
      {id:"architecture", t:"Architecture", ic:"\uD83C\uDFDB\uFE0F"},
      {id:"data-flow", t:"Data Flow", ic:"\uD83D\uDD00"}
    ]},
    {grp:"Backend internals", items:[
      {id:"execution-kernel", t:"Execution Kernel", ic:"\u2699\uFE0F"},
      {id:"manifests-compiler", t:"Manifests & Compiler", ic:"\uD83D\uDCDC"},
      {id:"capabilities", t:"Capabilities", ic:"\uD83E\uDDE9"},
      {id:"agents-runtime", t:"Agents & Runtime", ic:"\uD83E\uDD16"},
      {id:"api-data-model", t:"API & Data Model", ic:"\uD83D\uDD0C"}
    ]},
    {grp:"Frontend", items:[
      {id:"frontend", t:"Frontend App", ic:"\uD83D\uDDA5\uFE0F"},
      {id:"components", t:"Component Tree", ic:"\uD83E\uDDF1"},
      {id:"websocket-events", t:"WebSocket Events", ic:"\uD83D\uDCE1"}
    ]},
    {grp:"Product features", items:[
      {id:"pipeline-user-stories", t:"User Stories", ic:"\uD83D\uDCDD"},
      {id:"pipeline-ppt", t:"Presentations (PPT)", ic:"\uD83D\uDCCA"},
      {id:"pipeline-prototype", t:"Prototypes", ic:"\uD83C\uDFA8"},
      {id:"pipeline-app-builder", t:"App Builder", ic:"\uD83D\uDE80"},
      {id:"pipeline-modernization", t:"Modernization", ic:"\u267B\uFE0F"},
      {id:"feature-revisions", t:"Revisions", ic:"\u21A9\uFE0F"},
      {id:"feature-catalog-saved", t:"Catalog & Saved", ic:"\uD83D\uDDC2\uFE0F"},
      {id:"feature-handoff", t:"Claude-Code Handoff", ic:"\uD83E\uDD1D"}
    ]},
    {grp:"Cross-cutting", items:[
      {id:"feature-hitl-gates", t:"HITL & Clarify Gates", ic:"\uD83D\uDEA6"},
      {id:"feature-fanout-waves", t:"Fan-out & Waves", ic:"\uD83C\uDF0A"},
      {id:"feature-model-policy", t:"Model Policy", ic:"\uD83E\uDDE0"},
      {id:"feature-mcp-integrations", t:"MCP & Integrations", ic:"\uD83D\uDD17"},
      {id:"feature-skills-hooks", t:"Skills, Hooks, Guardrails", ic:"\uD83D\uDEE0\uFE0F"}
    ]},
    {grp:"Platform", items:[
      {id:"infrastructure", t:"Infrastructure", ic:"\u2601\uFE0F"},
      {id:"codebase-map", t:"Codebase Map", ic:"\uD83D\uDDC3\uFE0F"},
      {id:"phases", t:"22-Phase History", ic:"\uD83D\uDCC8"},
      {id:"security", t:"Security Notes", ic:"\uD83D\uDD12"},
      {id:"glossary", t:"Glossary", ic:"\uD83D\uDCD6"}
    ]}
  ];

  var page = document.body.getAttribute("data-page") || "index";
  var flat = [];
  NAV.forEach(function(g){ g.items.forEach(function(it){ flat.push(it); }); });
  function titleOf(id){ for(var i=0;i<flat.length;i++){ if(flat[i].id===id) return flat[i].t; } return id; }
  function href(id){ return id + ".html"; }
  function esc(s){ return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

  /* ---- render sidebar ---- */
  function renderNav(){
    var root = document.getElementById("nav-root");
    if(!root) return;
    var html = ''+
      '<aside class="sidebar" id="sidebar">'+
      '  <div class="brand"><div class="logo"><div class="mark">F</div>'+
      '    <div><div class="name">Flowin Docs</div><div class="sub">VelocityAI \u00B7 feature atlas</div></div></div></div>'+
      '  <div class="searchbox"><input id="navSearch" type="text" placeholder="Filter pages\u2026  (press /)" autocomplete="off"></div>'+
      '  <nav class="nav" id="nav">';
    NAV.forEach(function(g){
      html += '<div class="grp">'+esc(g.grp)+'</div>';
      g.items.forEach(function(it){
        var active = it.id===page ? ' active' : '';
        html += '<a class="navlink'+active+'" href="'+href(it.id)+'"><span class="ic">'+it.ic+'</span> '+esc(it.t)+'</a>';
      });
    });
    html += '</nav></aside>';
    root.innerHTML = html;

    var s = document.getElementById("navSearch");
    if(s){
      s.addEventListener("input", function(){
        var q=s.value.toLowerCase().trim();
        document.querySelectorAll('#nav .navlink').forEach(function(a){
          a.style.display = a.textContent.toLowerCase().indexOf(q)!==-1 ? '' : 'none';
        });
        document.querySelectorAll('#nav .grp').forEach(function(x){ x.style.display = q?'none':''; });
      });
    }
  }

  /* ---- topbar crumb + mobile toggle ---- */
  function wireTopbar(){
    var c = document.getElementById("crumb"); if(c) c.textContent = titleOf(page);
    var mb = document.getElementById("menuBtn");
    if(mb) mb.addEventListener("click", function(){ var sb=document.getElementById("sidebar"); if(sb) sb.classList.toggle("open"); });
  }

  /* ---- prev / next pager ---- */
  function renderPager(){
    var root = document.getElementById("pager-root");
    if(!root) return;
    var idx = flat.findIndex(function(x){ return x.id===page; });
    var prev = idx>0 ? flat[idx-1] : null;
    var next = idx>=0 && idx<flat.length-1 ? flat[idx+1] : null;
    var html='';
    html += prev ? '<a href="'+href(prev.id)+'"><div class="dir">\u2190 Previous</div><div class="ttl">'+esc(prev.t)+'</div></a>'
                 : '<a href="index.html"><div class="dir">\u2190 Previous</div><div class="ttl">Home</div></a>';
    html += next ? '<a class="next" href="'+href(next.id)+'"><div class="dir">Next \u2192</div><div class="ttl">'+esc(next.t)+'</div></a>'
                 : '<a class="next" href="index.html"><div class="dir">Next \u2192</div><div class="ttl">Back to Home</div></a>';
    root.innerHTML = html;
  }

  /* ---- interactive flow stepper ---- */
  function renderFlow(){
    var root = document.getElementById("flow-root");
    if(!root || !window.FLOW) return;
    var steps = window.FLOW;
    var nodes = steps.map(function(s,i){
      var badge = s.b ? ' <span class="badge '+(s.bc||'b-blue')+'">'+s.b+'</span>' : '';
      var rail = i<steps.length-1 ? '<div class="flow-rail"></div>' : '';
      return '<div class="flow-node'+(i===0?' on':'')+'" data-i="'+(i+1)+'">'+
        '<div class="num">'+(i+1)+'</div>'+
        '<div class="fbody"><div class="ft">'+s.t+badge+'</div><div class="fd">'+s.d+'</div></div></div>'+rail;
    }).join('');
    root.innerHTML =
      '<div class="flow-controls">'+
      '<button class="btn" id="fPrev">\u25C2 Prev</button>'+
      '<button class="btn primary" id="fNext">Next \u25B8</button>'+
      '<button class="btn" id="fAll">Show all</button>'+
      '<span class="dim" id="fLabel" style="margin-left:6px">Step 1 / '+steps.length+'</span></div>'+
      '<div class="flow" id="flow">'+nodes+'</div>';

    var els = Array.prototype.slice.call(root.querySelectorAll('.flow-node'));
    var idx=1, max=els.length;
    function draw(){
      els.forEach(function(n){ n.classList.toggle('on', parseInt(n.getAttribute('data-i'),10)===idx); });
      var lab=document.getElementById('fLabel'); if(lab) lab.textContent='Step '+idx+' / '+max;
      if(els[idx-1]) els[idx-1].scrollIntoView({behavior:'smooth',block:'center'});
    }
    document.getElementById('fNext').addEventListener('click',function(){ idx=Math.min(max,idx+1); draw(); });
    document.getElementById('fPrev').addEventListener('click',function(){ idx=Math.max(1,idx-1); draw(); });
    document.getElementById('fAll').addEventListener('click',function(){ els.forEach(function(n){n.classList.add('on');}); var l=document.getElementById('fLabel'); if(l) l.textContent='All '+max+' steps'; });
    els.forEach(function(n){ n.addEventListener('click',function(){ idx=parseInt(n.getAttribute('data-i'),10); draw(); }); });
  }

  /* ---- capability catalog (capabilities page) ---- */
  function renderCaps(){
    var grid=document.getElementById("capGrid");
    if(!grid || !window.CAP) return;
    var CAP=window.CAP, kinds=[]; CAP.forEach(function(c){ if(kinds.indexOf(c.k)===-1) kinds.push(c.k); });
    var filter="all";
    var pills=document.getElementById("capPills");
    var search=document.getElementById("capSearch");
    var cnt=document.getElementById("capCount"); if(cnt) cnt.textContent=CAP.length;
    function drawPills(){
      if(!pills) return;
      var h='<span class="pill '+(filter==="all"?"active":"")+'" data-k="all">All '+CAP.length+'</span>';
      kinds.forEach(function(k){ var c=CAP.filter(function(x){return x.k===k;}).length; h+='<span class="pill '+(filter===k?"active":"")+'" data-k="'+k+'">'+k+' '+c+'</span>'; });
      pills.innerHTML=h;
      pills.querySelectorAll('.pill').forEach(function(p){ p.addEventListener('click',function(){ filter=p.getAttribute('data-k'); drawPills(); draw(); }); });
    }
    function draw(){
      var q=(search&&search.value||"").toLowerCase().trim();
      var rows=CAP.filter(function(c){
        var okK=filter==="all"||c.k===filter;
        var okQ=!q||c.n.toLowerCase().indexOf(q)!==-1||c.k.toLowerCase().indexOf(q)!==-1||(c.d||"").toLowerCase().indexOf(q)!==-1;
        return okK&&okQ;
      });
      grid.innerHTML = rows.length ? rows.map(function(c){
        var trust=c.ua?'<span class="badge b-green">user-grantable</span>':'<span class="badge b-amber">gated</span>';
        return '<div class="cap"><div class="cn">'+esc(c.n)+'</div><div class="cd">'+esc(c.d)+'</div>'+
          '<div class="cm"><span class="badge b-blue">'+esc(c.k)+'</span>'+trust+'</div></div>';
      }).join('') : '<div class="muted">No capabilities match.</div>';
    }
    drawPills(); draw();
    if(search) search.addEventListener('input', draw);
  }

  /* ---- event table (websocket-events page) ---- */
  function renderEvents(){
    var body=document.getElementById("evBody");
    if(!body || !window.EV) return;
    var EV=window.EV, groups=[]; EV.forEach(function(e){ if(groups.indexOf(e.g)===-1) groups.push(e.g); });
    var bc={lifecycle:"b-blue",agent:"b-cyan",terminal:"b-red",reconnect:"b-blue",keepalive:"",planner:"b-violet",clarify:"b-amber",tools:"b-cyan",validation:"b-green",wave:"b-pink",audit:"b-amber",meta:""};
    var filter="all";
    var pills=document.getElementById("evPills");
    function drawPills(){
      if(!pills) return;
      var h='<span class="pill '+(filter==="all"?"active":"")+'" data-g="all">All '+EV.length+'</span>';
      groups.forEach(function(g){ var c=EV.filter(function(x){return x.g===g;}).length; h+='<span class="pill '+(filter===g?"active":"")+'" data-g="'+g+'">'+g+' '+c+'</span>'; });
      pills.innerHTML=h;
      pills.querySelectorAll('.pill').forEach(function(p){ p.addEventListener('click',function(){ filter=p.getAttribute('data-g'); drawPills(); draw(); }); });
    }
    function draw(){
      var rows=EV.filter(function(e){ return filter==="all"||e.g===filter; });
      body.innerHTML=rows.map(function(e){ return '<tr><td><code>'+esc(e.t)+'</code></td><td><span class="badge '+(bc[e.g]||"")+'">'+esc(e.g)+'</span></td><td>'+esc(e.d)+'</td></tr>'; }).join('');
    }
    drawPills(); draw();
  }

  /* ---- phase timeline (phases page) ---- */
  function renderPhases(){
    var root=document.getElementById("phaseTimeline");
    if(!root || !window.PHASES) return;
    root.innerHTML=window.PHASES.map(function(p){
      var planned=p[0]<=12;
      var col=planned?'linear-gradient(135deg,#5b8cff,#7c5cff)':'linear-gradient(135deg,#3ddc97,#37d5d6)';
      var tag=p[2]!=='-'?'<span class="badge b-violet">['+p[2]+']</span>':'<span class="badge b-green">post-v1.0</span>';
      return '<div style="display:flex;gap:14px;align-items:flex-start;padding:7px 0">'+
        '<div style="flex:0 0 auto;width:34px;height:34px;border-radius:9px;display:grid;place-items:center;font-weight:800;color:#fff;background:'+col+';box-shadow:0 6px 16px rgba(0,0,0,.3)">'+p[0]+'</div>'+
        '<div style="flex:1;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 14px">'+
        '<div style="font-weight:700;display:flex;gap:8px;align-items:center;flex-wrap:wrap">'+esc(p[1])+' '+tag+' <span class="badge b-green">\u2713</span></div>'+
        '<div class="muted" style="font-size:12.5px;margin-top:4px">'+esc(p[3])+'</div></div></div>';
    }).join('');
  }

  /* ---- back to top + hotkey ---- */
  function wireMisc(){
    var bt=document.getElementById("backtop");
    if(bt){ window.addEventListener('scroll',function(){ bt.classList.toggle('show', window.scrollY>500); }); bt.addEventListener('click',function(){ window.scrollTo({top:0,behavior:'smooth'}); }); }
    document.addEventListener('keydown',function(e){
      if(e.key==='/' && document.activeElement.tagName!=='INPUT'){ e.preventDefault(); var s=document.getElementById('navSearch'); if(s) s.focus(); }
    });
  }

  document.addEventListener("DOMContentLoaded", function(){
    renderNav(); wireTopbar(); renderPager();
    renderFlow(); renderCaps(); renderEvents(); renderPhases(); wireMisc();
  });
})();
