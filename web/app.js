(() => {
  const $=id=>document.getElementById(id);
  const editor=$('editor');
  const player=new CartridgePlayer($('screen'));
  let examples=[], current='square', currentFile='main.cvc', projectFiles={}, errorFile=null, busy=false, lastBuild=null, lastSource='', activeTab='diagnostics', errorLine=null;
  const outputs={diagnostics:'Pronto a compilare.',assembly:'Compila un programma per vedere il codice Z80.',basic:'Compila un programma per vedere il passaggio CVBasic.'};
  const escape=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const tokens=/\/\/[^\n]*|\/\*[\s\S]*?\*\/|"(?:\\.|[^"\\])*"|\b(?:uint8_t|uint16_t|void|const)\b|\b(?:if|else|while|do|for|switch|case|default|break|continue|return)\b|\b(?:setup|loop|waitFrame|waitVBlank|clearScreen|printAt|defineSprite|sprite|videoMode|screenEnable|screenDisable|spriteFlicker|vdpWrite|vramPoke|vramWrite|vramRead)\b|\b(?:0[xX][0-9a-fA-F]+|\d+)\b/g;
  function highlight(source){
    let result='',cursor=0;
    for(const match of source.matchAll(tokens)){
      result+=escape(source.slice(cursor,match.index));const t=match[0];
      const type=t.startsWith('/')?'comment':t.startsWith('"')?'string':/^\d/.test(t)?'number':/^(if|else|while|do|for|switch|case|default|break|continue|return)$/.test(t)?'keyword':/^(uint8_t|uint16_t|void|const)$/.test(t)?'type':'function';
      result+=`<span class="tok-${type}">${escape(t)}</span>`;cursor=match.index+t.length;
    }
    return result+escape(source.slice(cursor))+'\n';
  }
  function persist(){if(!Object.keys(projectFiles).length)return;projectFiles[currentFile]=editor.value;try{localStorage.setItem('cvcc-project-'+current,JSON.stringify(projectFiles));}catch{}}
  function projectText(){return JSON.stringify(projectFiles);}
  function updateEditor(){
    $('highlight').innerHTML=highlight(editor.value);
    const lines=editor.value.split('\n').length;
    $('line-numbers').textContent=Array.from({length:lines},(_,i)=>i+1).join('\n');
    $('source-lines').textContent=lines+' righe';
    const dirty=!!lastBuild&&(current!==lastBuild.name||projectText()!==lastSource);
    $('dirty-mark').hidden=!dirty;
    if(dirty)$('preview-note').textContent='Modifiche da compilare. Il player mostra l’ultima ROM valida.';
    updateCursor();syncScroll();
  }
  function updateCursor(){const prefix=editor.value.slice(0,editor.selectionStart);const lines=prefix.split('\n');$('cursor').textContent=`Ln ${lines.length}, Col ${lines.at(-1).length+1}`;}
  function syncScroll(){$('highlight').scrollTop=editor.scrollTop;$('highlight').scrollLeft=editor.scrollLeft;$('line-numbers').scrollTop=editor.scrollTop;}
  function renderTree(){
    const nav=$('project-tree');nav.replaceChildren();
    for(const project of examples){
      const folder=document.createElement('button');folder.className='file project-folder';folder.textContent=(project.id===current?'▾ ':'▸ ')+project.id+'/';
      folder.addEventListener('click',()=>choose(project.id));nav.append(folder);
      if(project.id===current) for(const name of Object.keys(projectFiles).sort((a,b)=>a==='main.cvc'?-1:b==='main.cvc'?1:a.localeCompare(b))){
        const file=document.createElement('button');file.className='file project-file'+(name===currentFile?' active':'');file.textContent=name;file.title=name;
        file.addEventListener('click',()=>chooseFile(name));nav.append(file);
      }
    }
  }
  function chooseFile(name){
    if(busy)return;persist();currentFile=name;editor.value=projectFiles[name];
    $('current-name').textContent=current+'/'+name;$('file-select').value=name;
    editor.scrollTop=0;editor.scrollLeft=0;updateEditor();renderTree();
  }
  function choose(id){
    if(busy)return;persist();current=id;const project=examples.find(e=>e.id===id);
    projectFiles={...project.files};
    try{const draft=JSON.parse(localStorage.getItem('cvcc-project-'+id)||'null');
      if(draft){for(const name of Object.keys(projectFiles))if(typeof draft[name]==='string')projectFiles[name]=draft[name];}
      if(!draft&&Object.keys(projectFiles).length===1){const legacy=localStorage.getItem('cvcc-draft-'+id);if(legacy!==null)projectFiles['main.cvc']=legacy;}
    }catch{}
    currentFile='main.cvc';editor.value=projectFiles[currentFile];
    $('example-select').value=id;$('file-select').replaceChildren(...Object.keys(projectFiles).map(name=>new Option(name,name)));
    $('current-name').textContent=id+'/main.cvc';$('file-select').value=currentFile;
    editor.scrollTop=0;editor.scrollLeft=0;updateEditor();renderTree();
  }
  function output(tab=activeTab){
    activeTab=tab;$('output').textContent=outputs[tab];
    $('output').classList.toggle('error',tab==='diagnostics'&&!!errorLine);
    $('goto-error').hidden=tab!=='diagnostics'||!errorLine;
    document.querySelectorAll('.output-tab').forEach(b=>{b.classList.toggle('active',b.dataset.tab===tab);b.setAttribute('aria-selected',String(b.dataset.tab===tab));});
  }
  function bytes(base64){return Uint8Array.from(atob(base64),ch=>ch.charCodeAt(0));}
  function saveFile(name,content,mime){
    const url=URL.createObjectURL(new Blob([content],{type:mime}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function selectedExport(){
    if(!lastBuild)return null;
    const selection=$('rom-format').value;
    if(selection==='original')return {rom:lastBuild.rom,size:lastBuild.rom_bytes,suffix:''};
    const item=lastBuild.exports?.find(item=>String(item.size)===selection);
    return item?{...item,suffix:'-'+(item.size/1024)+'KiB'}:null;
  }
  function updateDownload(){
    const item=selectedExport();
    $('download').disabled=!item;
    if(!item)return;
    $('download-size').textContent=`${item.size.toLocaleString('it-IT')} byte · codice e dati: ${lastBuild.code_bytes.toLocaleString('it-IT')} byte`;
    $('download').title='Scarica l’ultima ROM compilata: '+lastBuild.name+item.suffix+'.sg';
  }
  function exportChoices(){
    const select=$('rom-format'), previous=select.value;
    select.replaceChildren(new Option(`Originale (${lastBuild.rom_bytes/1024} KiB)`, 'original'));
    const choices=lastBuild.exports||[];
    for(const size of [8192,16384,32768,49152]){
      const available=choices.some(item=>item.size===size);
      const option=new Option(`${size/1024} KiB${available?'':' — non disponibile'}`,String(size));
      option.disabled=!available;select.add(option);
    }
    select.value=choices.some(item=>String(item.size)===previous)?previous:'original';
    select.disabled=false;updateDownload();
  }
  async function compile(){
    if(busy)return;busy=true;errorLine=null;persist();
    const files={...projectFiles},source=JSON.stringify(files),name=current;
    $('compile').disabled=true;$('compile-label').textContent='Compilazione…';
    $('build-duration').textContent='BUILD IN CORSO';$('build-dot').className='';$('status-text').textContent='Compilazione sul Mac…';
    outputs.diagnostics='→ Parsing Tree-sitter, controlli CVCC e compilazione della ROM…';output('diagnostics');
    try{
      const response=await fetch('/api/compile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({files})});
      const result=await response.json();
      if(!response.ok){errorLine=result.line||null;errorFile=result.file||null;throw new Error(result.error||'Compilazione non riuscita.');}
      lastBuild={...result,name};lastSource=source;
      outputs.assembly=result.assembly;outputs.basic=result.basic;
      outputs.diagnostics=`✓ Parsing e controlli semantici superati\n✓ ROM assemblata con sjasmplus · ${result.rom_bytes.toLocaleString('it-IT')} byte\n✓ Build completata in ${(result.elapsed_ms/1000).toFixed(2)} s\n\nSHA-256  ${result.sha256}`;
      $('build-duration').textContent=(result.elapsed_ms/1000).toFixed(2)+' s';$('build-dot').className='success';
      $('rom-size').innerHTML=(result.rom_bytes/1024)+'<small>KiB</small>';
      $('code-size').innerHTML=result.code_bytes.toLocaleString('it-IT')+'<small>byte</small>';
      $('ram-size').innerHTML=result.ram_bytes+'<small>byte</small>';
      exportChoices();
      $('status-text').textContent='Build riuscita · '+name+'.sg';
      try{
        await player.load(bytes(result.rom));
        $('empty-screen').hidden=true;$('pause-overlay').hidden=true;$('power-led').className='on';
        $('preview-state').textContent='IN ESECUZIONE';$('preview-state').className='preview-state live';
        $('fps').textContent=player.fps.toFixed(2)+' FPS';
        for(const id of ['pause','reset','sound'])$(id).disabled=false;
        $('pause').innerHTML='Ⅱ <span>Pausa</span>';
        $('preview-note').textContent='ROM in esecuzione. Clicca sullo schermo per usare frecce e Z/X. La compilazione resta locale.';
      }catch(error){
        outputs.diagnostics+='\n\nPlayer: '+error.message;
        $('preview-state').textContent='PLAYER NON DISPONIBILE';$('preview-state').className='preview-state';
        $('preview-note').textContent='ROM compilata e scaricabile. Il player non è disponibile.';
      }
    }catch(error){
      outputs.diagnostics=error.message;$('build-dot').className='failure';$('build-duration').textContent='ERRORE';
      $('status-text').textContent='Build non riuscita';
      $('preview-note').textContent=lastBuild?'Build non riuscita. Il player e il download mantengono l’ultima ROM valida.':'Correggi il sorgente e ricompila. Nessuna ROM generata.';
    }finally{busy=false;$('compile').disabled=false;$('compile-label').textContent='Compila e avvia';updateEditor();output('diagnostics');}
  }
  editor.addEventListener('input',()=>{persist();updateEditor();});
  editor.addEventListener('scroll',syncScroll);editor.addEventListener('click',updateCursor);editor.addEventListener('keyup',updateCursor);
  editor.addEventListener('keydown',event=>{
    if(event.key==='Tab'){
      event.preventDefault();const start=editor.selectionStart,end=editor.selectionEnd;
      editor.setRangeText('    ',start,end,'end');persist();updateEditor();
    }
  });
  document.addEventListener('keydown',event=>{if((event.metaKey||event.ctrlKey)&&event.key==='Enter'){event.preventDefault();void compile();}});
  $('file-select').addEventListener('change',()=>{if(busy){$('file-select').value=currentFile;return;}chooseFile($('file-select').value);});
  document.querySelectorAll('.output-tab').forEach(b=>b.addEventListener('click',()=>output(b.dataset.tab)));
  $('compile').addEventListener('click',compile);
  $('example-select').addEventListener('change',()=>{if(busy){$('example-select').value=current;return;}choose($('example-select').value);});
  $('goto-error').addEventListener('click',()=>{if(!errorLine)return;if(errorFile&&Object.hasOwn(projectFiles,errorFile))chooseFile(errorFile);const lines=editor.value.split('\n');const start=lines.slice(0,errorLine-1).reduce((sum,line)=>sum+line.length+1,0);editor.focus();editor.setSelectionRange(start,start+(lines[errorLine-1]||'').length);editor.scrollTop=Math.max(0,(errorLine-4)*22);syncScroll();updateCursor();});
  $('save-source').addEventListener('click',()=>saveFile(currentFile.split('/').at(-1),editor.value,'text/plain'));
  $('save-project').addEventListener('click',async()=>{
    persist();const name=current;
    try{const response=await fetch('/api/project-download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({files:projectFiles})});
      if(!response.ok)throw new Error((await response.json()).error);
      saveFile(name+'.zip',await response.arrayBuffer(),'application/zip');
    }catch(error){outputs.diagnostics=error.message;output('diagnostics');}
  });
  $('rom-format').addEventListener('change',updateDownload);
  $('download').addEventListener('click',()=>{const item=selectedExport();if(item)saveFile(lastBuild.name+item.suffix+'.sg',bytes(item.rom),'application/octet-stream');});
  $('pause').addEventListener('click',()=>{const paused=player.pause();$('pause-overlay').hidden=!paused;$('pause').innerHTML=paused?'▶ <span>Riprendi</span>':'Ⅱ <span>Pausa</span>';$('preview-state').textContent=paused?'IN PAUSA':'IN ESECUZIONE';$('preview-state').classList.toggle('live',!paused);});
  $('reset').addEventListener('click',()=>player.reset());
  $('sound').addEventListener('click',async()=>{try{const on=await player.sound();$('sound').innerHTML='♪ <span>Audio '+(on?'on':'off')+'</span>';}catch(error){outputs.diagnostics+='\nAudio: '+error.message;output('diagnostics');}});
  $('reference-button').addEventListener('click',()=>$('reference').showModal());$('close-reference').addEventListener('click',()=>$('reference').close());
  fetch('/api/config').then(async response=>{if(!response.ok)throw new Error('Server non disponibile');return response.json();}).then(config=>{
    examples=config.examples;
    $('example-select').replaceChildren(...examples.map(project=>new Option(project.id,project.id)));
    choose('square');$('server-led').className='online';$('connection-label').textContent='LOCALE';$('compile').disabled=false;
    outputs.diagnostics='✓ Compilatore locale pronto.\nAvvio del primo esempio…';output();void compile();
  }).catch(error=>{$('connection-label').textContent='OFFLINE';outputs.diagnostics=error.message;output();});
})();
