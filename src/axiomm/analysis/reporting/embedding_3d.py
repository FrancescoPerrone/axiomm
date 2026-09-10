"""On-demand 3-D embedding viewer (stage two).

An interactive WebGL point cloud of the reduction embedding (>=3 components),
coloured by cluster. It is an **opt-in, on-demand** viewer (a UX adapter): it loads
three.js from a CDN, so — unlike the self-contained report — it needs network access
the first time; the desktop app will bundle it, and a native VTK viewer is the
heavier desktop path.

**Scientifically gated:** the axes are reduced components, not physical quantities;
for UMAP especially, distances/directions are not metric — an exploratory view.

Interaction (no auto-spin): drag to orbit, wheel to zoom, shift/right-drag to pan,
reset to re-fit; per-cluster legend toggles, a point-size control, a
perspective/orthographic switch, and an axes triad — the conventions of a general
scientific 3-D scatter. The control styling is deliberately plain (to be revisited
at the UX stage).
"""

from __future__ import annotations

import json

import numpy as np

from axiomm.analysis.errors import PayloadValidationError

_PALETTE = (
    "#4c78a8", "#f58518", "#54a24b", "#e45756", "#72b7b2", "#b279a2",
    "#ff9da6", "#9d755d", "#eeca3b", "#b39ddb", "#8cd17d", "#d37295",
)
_THREE = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"


def embedding_3d_from_result(result, *, max_points: int = 6000, seed: int = 0):
    """Extract a 3-D embedding (first 3 components) + per-pixel cluster labels."""
    decomp = getattr(result, "decomposition", None)
    clustering = getattr(result, "clustering", None)
    if decomp is None or clustering is None:
        raise PayloadValidationError("a 3-D embedding needs a decomposition and clustering.")
    loadings = np.asarray(decomp.loadings, dtype=float)
    if loadings.ndim != 2 or loadings.shape[1] < 3:
        raise PayloadValidationError(
            "the 3-D viewer needs >=3 components; run the reduction with n_components>=3 "
            f"(got shape {loadings.shape}).")
    points = loadings[:, :3]
    labels = np.asarray(clustering.labels)
    if points.shape[0] > max_points:
        sel = np.random.default_rng(seed).choice(points.shape[0], max_points, replace=False)
        points, labels = points[sel], labels[sel]
    return points, labels


def render_embedding_3d_page(points, labels, *, title: str = "Embedding",
                             backend: str = "reduction") -> str:
    """A self-loading interactive 3-D scatter page (three.js from CDN)."""
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise PayloadValidationError(f"points must be (n, 3); got shape {pts.shape}.")
    labels = np.asarray(labels)
    categories = [int(c) for c in np.unique(labels)]
    colors = {c: ("#8a8f98" if c == -1 else _PALETTE[i % len(_PALETTE)])
              for i, c in enumerate(categories)}
    data = {
        "points": [round(float(v), 4) for v in pts.reshape(-1)],
        "labels": [int(v) for v in labels],
        "categories": categories,
        "colors": [colors[c] for c in categories],
        "names": ["noise" if c == -1 else f"cluster {c}" for c in categories],
        "axisLabels": [f"{backend} 1", f"{backend} 2", f"{backend} 3"],
    }
    return _PAGE.replace("/*DATA*/", json.dumps(data)).replace("__TITLE__", _esc(title)) \
        .replace("__THREE__", _THREE).replace("__BACKEND__", _esc(backend))


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>__TITLE__</title>
<style>
:root{ --bg:#0e1114; --ink:#e7ebef; --muted:#97a2af; --border:#29313a; --accent:#3bbcc9;
  --surface:#161a1f; --sans:'IBM Plex Sans',system-ui,sans-serif; --mono:'IBM Plex Mono',ui-monospace,monospace; }
@media (prefers-color-scheme:light){:root{ --bg:#f5f7f8; --ink:#14181d; --muted:#5c6673; --border:#dbe1e7;
  --accent:#0d7d88; --surface:#ffffff; }}
html,body{height:100%;} body{margin:0; background:var(--bg); color:var(--ink); font-family:var(--sans); overflow:hidden;}
#view{position:fixed; inset:0; touch-action:none;}
.head{position:fixed; top:1rem; left:1.25rem; z-index:5; pointer-events:none;}
.head .eyebrow{font-family:var(--mono); font-size:.72rem; letter-spacing:.14em; text-transform:uppercase; color:var(--accent); margin:0 0 .25rem;}
.head h1{font-size:1.3rem; font-weight:600; margin:0;}
.head p{color:var(--muted); font-size:.82rem; margin:.3rem 0 0; max-width:34rem;}
.panel{position:fixed; top:1rem; right:1rem; z-index:5; background:color-mix(in srgb,var(--surface) 88%,transparent);
  border:1px solid var(--border); border-radius:10px; padding:.8rem .9rem; font-size:.72rem; font-family:var(--mono);
  display:flex; flex-direction:column; gap:.55rem; min-width:11rem; backdrop-filter:blur(6px);}
.panel .row{display:flex; align-items:center; justify-content:space-between; gap:.6rem;}
.panel button{border:1px solid var(--border); background:var(--surface); color:var(--muted); border-radius:6px;
  padding:.25rem .55rem; cursor:pointer; font-family:var(--mono); font-size:.68rem;}
.panel button.on{border-color:var(--accent); color:var(--accent);}
.panel input[type=range]{width:6.5rem;}
.legend{display:flex; flex-direction:column; gap:.3rem; margin-top:.15rem; border-top:1px solid var(--border); padding-top:.5rem;}
.legend .item{display:flex; align-items:center; gap:.45rem; cursor:pointer; opacity:.55; transition:opacity .15s;}
.legend .item.on{opacity:1;} .legend .sw{width:.75rem; height:.75rem; border-radius:3px;}
</style></head><body>
<canvas id="view"></canvas>
<div class="head"><p class="eyebrow">AXIOMM · __BACKEND__ embedding</p><h1>__TITLE__</h1>
<p>Pixels in the reduction space, coloured by cluster. Axes are reduced components, not physical quantities — an exploratory view, not a validated result.</p></div>
<div class="panel">
  <div class="row"><span>reset</span><button id="reset">re-fit</button></div>
  <div class="row"><span>projection</span><button id="proj">perspective</button></div>
  <div class="row"><span>point size</span><input id="size" type="range" min="1" max="12" step="0.5" value="4"></div>
  <div class="row"><span>axes</span><button id="axes" class="on">on</button></div>
  <div class="legend" id="legend"></div>
</div>
<script src="__THREE__"></script>
<script>
(function(){
  var D = /*DATA*/;
  var cvs = document.getElementById('view');
  var scene = new THREE.Scene();
  var W = window.innerWidth, H = window.innerHeight;
  var renderer = new THREE.WebGLRenderer({canvas:cvs, antialias:true, alpha:true});
  renderer.setPixelRatio(window.devicePixelRatio||1); renderer.setSize(W,H);

  // build one Points object per category (for legend toggling)
  var pos = D.points, lab = D.labels;
  var n = lab.length;
  var cx=0,cy=0,cz=0, minx=1e9,miny=1e9,minz=1e9,maxx=-1e9,maxy=-1e9,maxz=-1e9;
  for(var i=0;i<n;i++){var x=pos[i*3],y=pos[i*3+1],z=pos[i*3+2];cx+=x;cy+=y;cz+=z;
    minx=Math.min(minx,x);maxx=Math.max(maxx,x);miny=Math.min(miny,y);maxy=Math.max(maxy,y);minz=Math.min(minz,z);maxz=Math.max(maxz,z);}
  cx/=n;cy/=n;cz/=n;
  var span=Math.max(maxx-minx,maxy-miny,maxz-minz)||1;
  var group=new THREE.Group(); scene.add(group);
  var byCat={}, meshes=[];
  D.categories.forEach(function(cat,ci){
    var xs=[]; for(var i=0;i<n;i++) if(lab[i]===cat){xs.push(pos[i*3]-cx,pos[i*3+1]-cy,pos[i*3+2]-cz);}
    var g=new THREE.BufferGeometry(); g.setAttribute('position',new THREE.Float32BufferAttribute(xs,3));
    var m=new THREE.PointsMaterial({color:new THREE.Color(D.colors[ci]), size:4, sizeAttenuation:true, transparent:true, opacity:.9});
    var pts=new THREE.Points(g,m); group.add(pts); meshes.push(pts); byCat[cat]=pts;
  });
  var axes=new THREE.AxesHelper(span*0.6); scene.add(axes);

  // cameras
  var aspect=W/H, r0=span*1.9;
  var persp=new THREE.PerspectiveCamera(45,aspect,span*0.01,span*100);
  var oh=span*1.2; var ortho=new THREE.OrthographicCamera(-oh*aspect,oh*aspect,oh,-oh,-span*100,span*100);
  var cam=persp, target=new THREE.Vector3(0,0,0);
  // spherical orbit state (no auto-rotation)
  var theta=0.9, phi=1.1, radius=r0;
  function place(){ var s=Math.sin(phi);
    cam.position.set(target.x+radius*s*Math.cos(theta), target.y+radius*Math.cos(phi), target.z+radius*s*Math.sin(theta));
    cam.lookAt(target); if(cam.updateProjectionMatrix)cam.updateProjectionMatrix(); }
  function render(){ place(); renderer.render(scene,cam); }

  // hand-rolled orbit / zoom / pan controls
  var drag=null,px,py;
  cvs.addEventListener('pointerdown',function(e){drag=(e.button===2||e.shiftKey)?'pan':'orbit';px=e.clientX;py=e.clientY;cvs.setPointerCapture(e.pointerId);});
  cvs.addEventListener('contextmenu',function(e){e.preventDefault();});
  cvs.addEventListener('pointermove',function(e){ if(!drag)return; var dx=e.clientX-px,dy=e.clientY-py; px=e.clientX;py=e.clientY;
    if(drag==='orbit'){ theta-=dx*0.01; phi=Math.max(0.05,Math.min(Math.PI-0.05,phi-dy*0.01)); }
    else { var pan=radius*0.0016; var right=new THREE.Vector3().subVectors(cam.position,target).cross(cam.up).normalize();
      var up=cam.up.clone().normalize(); target.addScaledVector(right,-dx*pan); target.addScaledVector(up,dy*pan); }
    render(); });
  cvs.addEventListener('pointerup',function(){drag=null;});
  cvs.addEventListener('wheel',function(e){e.preventDefault(); radius*=(1+Math.sign(e.deltaY)*0.08);
    radius=Math.max(span*0.2,Math.min(span*20,radius)); if(cam===ortho){oh*=(1+Math.sign(e.deltaY)*0.08); ortho.left=-oh*aspect;ortho.right=oh*aspect;ortho.top=oh;ortho.bottom=-oh;} render();},{passive:false});

  // UI
  document.getElementById('reset').onclick=function(){theta=0.9;phi=1.1;radius=r0;oh=span*1.2;target.set(0,0,0);
    ortho.left=-oh*aspect;ortho.right=oh*aspect;ortho.top=oh;ortho.bottom=-oh;render();};
  var proj=document.getElementById('proj');
  proj.onclick=function(){ cam=(cam===persp)?ortho:persp; proj.textContent=(cam===persp)?'perspective':'orthographic'; render();};
  document.getElementById('size').oninput=function(e){var s=parseFloat(e.target.value);meshes.forEach(function(m){m.material.size=s;});render();};
  var axBtn=document.getElementById('axes');
  axBtn.onclick=function(){axes.visible=!axes.visible;axBtn.classList.toggle('on',axes.visible);axBtn.textContent=axes.visible?'on':'off';render();};
  var leg=document.getElementById('legend');
  D.categories.forEach(function(cat,ci){var it=document.createElement('div');it.className='item on';
    it.innerHTML='<span class="sw" style="background:'+D.colors[ci]+'"></span>'+D.names[ci];
    it.onclick=function(){var v=!byCat[cat].visible;byCat[cat].visible=v;it.classList.toggle('on',v);render();};leg.appendChild(it);});

  window.addEventListener('resize',function(){W=window.innerWidth;H=window.innerHeight;aspect=W/H;
    renderer.setSize(W,H);persp.aspect=aspect;persp.updateProjectionMatrix();
    ortho.left=-oh*aspect;ortho.right=oh*aspect;ortho.top=oh;ortho.bottom=-oh;ortho.updateProjectionMatrix();render();});
  render();   // static initial view — never auto-spins
})();
</script></body></html>
"""


__all__ = ["embedding_3d_from_result", "render_embedding_3d_page"]
