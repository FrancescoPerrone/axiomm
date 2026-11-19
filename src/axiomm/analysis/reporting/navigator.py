"""Raw-data navigator fragment for the report — a HyperSpy ``map.plot()``-style
summed-intensity map whose pixels can be explored for their spectrum.

Headless and dependency-light: no matplotlib, no GUI. The section embeds a small
uint8 intensity image (drawn instantly as the clickable preview) and the binned
spectral cube **gzip-compressed** (XRF spectra are mostly zeros, so this is tiny);
the browser decompresses it with the native ``DecompressionStream`` only when the
reader opens the modal. Clicking the preview opens a full-screen navigator over a
blurred report (``backdrop-filter``); hovering a pixel reads its spectrum.
"""

from __future__ import annotations

import base64
import gzip

import numpy as np


def _bin_cube(data: np.ndarray, sbin: int, ebin: int) -> np.ndarray:
    ny, nx, ne = data.shape
    ny2, nx2, ne2 = max(1, ny // sbin), max(1, nx // sbin), max(1, ne // ebin)
    c = data[: ny2 * sbin, : nx2 * sbin, : ne2 * ebin]
    return c.reshape(ny2, sbin, nx2, sbin, ne2, ebin).sum(axis=(1, 3, 5))


def navigator_markup(payload, *, spatial_bin: int = 2, energy_bin: int = 8) -> str:
    """Build the self-contained navigator HTML fragment for ``payload``."""
    data = np.asarray(payload.data, dtype=np.float64)
    if data.ndim != 3:
        raise ValueError(f"navigator needs a 3-D (ny, nx, ne) cube; got {data.shape}.")
    sig = next(a for a in payload.axes if a.role == "signal")
    e0 = float(sig.offset)
    de = float(sig.scale) * int(energy_bin)

    binned = _bin_cube(data, int(spatial_bin), int(energy_bin))
    ny, nx, ne = binned.shape
    mx = float(binned.max()) or 1.0
    q = np.clip(np.round(binned / mx * 65535.0), 0, 65535).astype("<u2")
    cube_b64 = base64.b64encode(gzip.compress(q.tobytes(), 6)).decode("ascii")

    imap = binned.sum(axis=-1)
    imap = (imap / (float(imap.max()) or 1.0) * 255.0).astype(np.uint8)
    imap_b64 = base64.b64encode(imap.tobytes()).decode("ascii")

    return _TMPL \
        .replace("__NY__", str(ny)).replace("__NX__", str(nx)).replace("__NE__", str(ne)) \
        .replace("__E0__", f"{e0:.5f}").replace("__DE__", f"{de:.6f}") \
        .replace("__MX__", f"{mx:.6f}") \
        .replace("__IMAP__", imap_b64).replace("__CUBE__", cube_b64)


# Classes/ids are axm-nav-scoped so the fragment never collides with the report.
_TMPL = r"""<div class="axm-nav">
  <canvas class="axm-nav-thumb" id="axm-nav-thumb" title="Click to explore pixel-by-pixel"></canvas>
</div>
<div class="axm-nav-modal" id="axm-nav-modal" role="dialog" aria-modal="true" hidden>
  <div class="axm-nav-dialog">
    <button class="axm-nav-close" id="axm-nav-close" aria-label="Close">&times;</button>
    <div class="axm-nav-grid">
      <div><canvas id="axm-nav-map"></canvas><div class="axm-nav-pos" id="axm-nav-pos">&nbsp;</div></div>
      <div><canvas id="axm-nav-spec" width="520" height="340"></canvas>
        <div class="axm-nav-hint">Energy (keV) → · hover a pixel · click to pin</div></div>
    </div>
  </div>
</div>
<style>
  .axm-nav-thumb { image-rendering:pixelated; width:100%; max-width:320px; border-radius:7px;
    cursor:zoom-in; display:block; background:#111; }
  .axm-nav-modal { position:fixed; inset:0; z-index:9999; display:flex; align-items:center;
    justify-content:center; padding:20px; background:rgba(10,12,16,.45);
    -webkit-backdrop-filter:blur(7px); backdrop-filter:blur(7px); }
  .axm-nav-modal[hidden] { display:none; }
  .axm-nav-dialog { position:relative; background:var(--panel,#12151a); color:var(--fg,#e8eaed);
    border:1px solid var(--border,#2a2f37); border-radius:14px; padding:18px 18px 14px;
    box-shadow:0 24px 64px rgba(0,0,0,.4); max-width:min(960px,96vw); max-height:92vh; overflow:auto; }
  .axm-nav-grid { display:flex; flex-wrap:wrap; gap:18px; align-items:flex-start; }
  #axm-nav-map { image-rendering:pixelated; cursor:crosshair; border-radius:7px; background:#111; }
  .axm-nav-close { position:absolute; top:8px; right:10px; border:0; background:transparent;
    color:var(--muted,#9aa0a6); font-size:1.5rem; line-height:1; cursor:pointer; }
  .axm-nav-close:hover { color:var(--fg,#e8eaed); }
  .axm-nav-pos, .axm-nav-hint { color:var(--muted,#9aa0a6); font-size:.8rem;
    font-variant-numeric:tabular-nums; margin-top:6px; }
</style>
<script>
(function(){
  var NY=__NY__, NX=__NX__, NE=__NE__, E0=__E0__, DE=__DE__, MX=__MX__;
  function unb64(s){ var b=atob(s), a=new Uint8Array(b.length); for(var i=0;i<b.length;i++)a[i]=b.charCodeAt(i); return a; }
  var imap=unb64("__IMAP__");
  // instant preview thumbnail (no decompression needed)
  function paintGray(canvas, scaleUp){
    var S=scaleUp||Math.max(2, Math.floor(360/Math.max(NY,NX)));
    canvas.width=NX*S; canvas.height=NY*S;
    var g=canvas.getContext('2d'), off=document.createElement('canvas'); off.width=NX; off.height=NY;
    var im=off.getContext('2d').createImageData(NX,NY);
    for(var i=0;i<NY*NX;i++){ var v=imap[i]; im.data[i*4]=v; im.data[i*4+1]=v; im.data[i*4+2]=v; im.data[i*4+3]=255; }
    off.getContext('2d').putImageData(im,0,0);
    g.imageSmoothingEnabled=false; g.drawImage(off,0,0,NX,NY,0,0,canvas.width,canvas.height);
    return S;
  }
  paintGray(document.getElementById('axm-nav-thumb'));

  var modal=document.getElementById('axm-nav-modal'), cube=null, mapS=1;
  async function gunzip(u8){
    if(typeof DecompressionStream==='undefined') return null;
    var s=new Blob([u8]).stream().pipeThrough(new DecompressionStream('gzip'));
    return new Uint16Array(await new Response(s).arrayBuffer());
  }
  function drawSpec(px,py,pinned){
    var spec=document.getElementById('axm-nav-spec'), sg=spec.getContext('2d');
    var W=spec.width,H=spec.height,x0=44,x1=W-10,y0=H-26,y1=10;
    sg.clearRect(0,0,W,H);
    var base=(py*NX+px)*NE, EMAX=Math.min(E0+NE*DE,20), nshow=Math.max(2,Math.round((EMAX-E0)/DE));
    var mxv=1,k; for(k=0;k<nshow;k++){ if(cube[base+k]>mxv)mxv=cube[base+k]; }
    sg.strokeStyle='#3a3f47'; sg.beginPath(); sg.moveTo(x0,y1); sg.lineTo(x0,y0); sg.lineTo(x1,y0); sg.stroke();
    sg.fillStyle='#9aa0a6'; sg.font='11px sans-serif';
    for(var ek=0;ek<=EMAX;ek+=5){ var xx=x0+(ek-E0)/(EMAX-E0)*(x1-x0); sg.fillText(ek+'',xx-4,y0+15);
      sg.strokeStyle='#23272e'; sg.beginPath(); sg.moveTo(xx,y1); sg.lineTo(xx,y0); sg.stroke(); }
    sg.strokeStyle=pinned?'#e6a15a':'#5aa9e6'; sg.lineWidth=1.4; sg.beginPath();
    for(k=0;k<nshow;k++){ var x=x0+k/(nshow-1)*(x1-x0), y=y0-(cube[base+k]/mxv)*(y0-y1); k?sg.lineTo(x,y):sg.moveTo(x,y); }
    sg.stroke();
    sg.fillStyle='#9aa0a6'; sg.fillText('peak '+Math.round(mxv/65535*MX)+' cts', x1-96, y1+4);
  }
  var pinned=false;
  function onHover(ev,pin){
    var map=document.getElementById('axm-nav-map'), r=map.getBoundingClientRect();
    var px=Math.floor((ev.clientX-r.left)/map.width*NX), py=Math.floor((ev.clientY-r.top)/map.height*NY);
    if(px<0||py<0||px>=NX||py>=NY) return;
    document.getElementById('axm-nav-pos').textContent='pixel ('+px+', '+py+')';
    drawSpec(px,py,pin);
  }
  async function openModal(){
    document.body.appendChild(modal);   // escape the report card's stacking context
    modal.hidden=false;
    if(!cube){
      cube=await gunzip(unb64("__CUBE__"));
      if(!cube){ document.getElementById('axm-nav-pos').textContent='spectra need a current browser (DecompressionStream)'; return; }
      var map=document.getElementById('axm-nav-map'); mapS=paintGray(map);
      map.addEventListener('mousemove', function(e){ if(!pinned) onHover(e,false); });
      map.addEventListener('click', function(e){ pinned=!pinned; onHover(e,pinned); });
      drawSpec(Math.floor(NX/2),Math.floor(NY/2),false);
    }
  }
  function closeModal(){ modal.hidden=true; }
  document.getElementById('axm-nav-thumb').addEventListener('click', openModal);
  document.getElementById('axm-nav-close').addEventListener('click', closeModal);
  modal.addEventListener('click', function(e){ if(e.target===modal) closeModal(); });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape' && !modal.hidden) closeModal(); });
})();
</script>"""
