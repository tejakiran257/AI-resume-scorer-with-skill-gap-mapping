// show fake "processing" modal to feel realtime (used on results if you want)
function showProcessing(duration=1200){
  const el = document.createElement('div');
  el.innerHTML = `<div style="position:fixed;inset:0;display:flex;align-items:center;justify-content:center;z-index:9999">
    <div style="background:rgba(0,0,0,0.6);padding:2rem;border-radius:12px;color:white;display:flex;flex-direction:column;align-items:center">
      <div class="spinner-border text-light" role="status" style="width:3rem;height:3rem"></div>
      <div style="margin-top:1rem">Analyzing resume — please wait...</div>
    </div></div>`;
  document.body.appendChild(el);
  setTimeout(()=>el.remove(), duration);
}