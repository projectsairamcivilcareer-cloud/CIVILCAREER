/* Civil Career: remove accidental duplicate action controls within the same UI group.
   Keeps one control for an identical destination + label in a section/card/form;
   does not remove same links from separate cards or navigation groups. */
(()=> {
  const clean=()=>{
    const groups=document.querySelectorAll('section,article,form,.card,.content-box,.actions,.button-group,.btn-group,.alert-actions,.card-actions,.profile-options');
    groups.forEach(group=>{
      const seen=new Set();
      group.querySelectorAll('a,button,input[type="button"],input[type="submit"]').forEach(el=>{
        if(el.dataset.keepDuplicate==='true'||el.hidden||el.getAttribute('aria-hidden')==='true')return;
        const label=(el.innerText||el.value||el.getAttribute('aria-label')||el.title||'').replace(/\s+/g,' ').trim().toLowerCase();
        const href=(el.getAttribute('href')||el.getAttribute('formaction')||el.getAttribute('type')||'').trim();
        if(!label&&!href)return;
        const key=label+'|'+href;
        if(seen.has(key)){el.remove();}else{seen.add(key);}
      });
    });
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',clean,{once:true});else clean();
})();