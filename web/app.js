(() => {
  const $=id=>document.getElementById(id);
  const editor=$('editor');
  let workspace=null;
  const player=new CartridgePlayer($('screen'));
  let cartridgeProfiles=[];
  let examples=[], current='square', currentFile='main.cvc', projectFiles={}, errorFile=null, busy=false, lastBuild=null, lastSource='', activeTab='diagnostics', errorLine=null;
  const outputs={diagnostics:'Pronto a compilare.',assembly:'Compila un programma per vedere il codice Z80.'};
  const escape=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const tokens=/\/\/[^\n]*|\/\*[\s\S]*?\*\/|"(?:\\.|[^"\\])*"|\b(?:uint8_t|uint16_t|void|const)\b|\b(?:if|else|while|do|for|switch|case|default|break|continue|return)\b|\b(?:setup|loop|sound|soundVolume|bankRead|vramWriteBank|controllerRead|waitFrame|waitVBlank|clearScreen|printAt|defineSprite|sprite|videoMode|screenEnable|screenDisable|spriteFlicker|vdpWrite|vramPoke|vramWrite|vramRead)\b|\b(?:0[xX][0-9a-fA-F]+|\d+)\b/g;
  function highlight(source){
    let result='',cursor=0;
    for(const match of source.matchAll(tokens)){
      result+=escape(source.slice(cursor,match.index));const t=match[0];
      const type=t.startsWith('/')?'comment':t.startsWith('"')?'string':/^\d/.test(t)?'number':/^(if|else|while|do|for|switch|case|default|break|continue|return)$/.test(t)?'keyword':/^(uint8_t|uint16_t|void|const)$/.test(t)?'type':'function';
      result+=`<span class="tok-${type}">${escape(t)}</span>`;cursor=match.index+t.length;
    }
    return result+escape(source.slice(cursor))+'\n';
  }
  function persist(){
    if(!Object.keys(projectFiles).length)return;
    if(typeof projectFiles[currentFile]==='string')projectFiles[currentFile]=editor.value;
    let saved=true;
    try{localStorage.setItem('cvcc-project-'+current,JSON.stringify(projectFiles));}catch{saved=false;}
    workspace?.changed(saved);
  }
  function projectText(){return JSON.stringify(projectFiles);}
  function updateEditor(){
    $('highlight').innerHTML=highlight(editor.value);
    const lines=editor.value.split('\n').length;
    $('line-numbers').textContent=Array.from({length:lines},(_,i)=>i+1).join('\n');
    $('source-lines').textContent=editor.readOnly?bytes(projectFiles[currentFile].base64).length+' byte · sola lettura':lines+' righe';
    const dirty=!!lastBuild&&(current!==lastBuild.projectId||projectText()!==lastSource);
    $('dirty-mark').hidden=!dirty;
    if(dirty)$('preview-note').textContent='Modifiche da compilare. Il player mostra l’ultima ROM valida.';
    updateCursor();syncScroll();updateCartridge();
  }
  function updateCursor(){const prefix=editor.value.slice(0,editor.selectionStart);const lines=prefix.split('\n');$('cursor').textContent=`Ln ${lines.length}, Col ${lines.at(-1).length+1}`;}
  function syncScroll(){$('highlight').scrollTop=editor.scrollTop;$('highlight').scrollLeft=editor.scrollLeft;$('line-numbers').scrollTop=editor.scrollTop;}
  // Folder state belongs to each project; switching files must not flatten it.
  const openFolders=new Map(), closedProjects=new Set();
  function foldersForProject(){
    if(!openFolders.has(current))openFolders.set(current,new Set());
    return openFolders.get(current);
  }
  function revealFile(name){
    closedProjects.delete(current);
    const parts=name.split('/');parts.pop();
    for(let i=1;i<=parts.length;i++)foldersForProject().add(parts.slice(0,i).join('/'));
  }
  function fileIcon(kind,open=false){
    const icon=document.createElement('span');icon.className='file-icon icon-'+kind;icon.setAttribute('aria-hidden','true');
    if(kind==='folder'){
      // Inline vector icons stay crisp and require no external assets.
      const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');
      const path=document.createElementNS(svg.namespaceURI,'path');
      path.setAttribute('d',open?'M3 7V5h6l2 2h10v3H7L3 19V7Zm0 12 4-9h15l-4 9H3Z':'M3 7V5h6l2 2h10v14H3V7Z');
      svg.append(path);icon.append(svg);
    }else icon.textContent=kind==='binary'?'01':kind==='header'?'H':'C';
    return icon;
  }
  function treeButton(label,kind,open=false){
    const button=document.createElement('button');button.type='button';button.className='file';
    if(kind==='folder'){
      const arrow=document.createElement('span');arrow.className='folder-arrow';arrow.textContent=open?'▾':'▸';arrow.setAttribute('aria-hidden','true');button.append(arrow);
      button.setAttribute('aria-expanded',String(open));
    }
    button.append(fileIcon(kind,open));
    const text=document.createElement('span');text.className='file-label';text.textContent=label;button.append(text);
    return button;
  }
  function renderTree(){
    const nav=$('project-tree');nav.replaceChildren();
    for(const project of examples){
      const expanded=project.id===current&&!closedProjects.has(project.id);
      const folder=treeButton(project.label||project.id,'folder',expanded);folder.classList.add('project-folder');
      folder.addEventListener('click',()=>{
        if(busy||workspace?.pending)return;
        if(project.id!==current){closedProjects.delete(project.id);choose(project.id);}
        else{if(closedProjects.has(current))closedProjects.delete(current);else closedProjects.add(current);renderTree();}
      });nav.append(folder);
      if(!expanded)continue;
      const root=new Map();
      for(const name of Object.keys(projectFiles)){
        const parts=name.split('/');let children=root;
        parts.forEach((part,index)=>{
          if(!children.has(part))children.set(part,{name:part,path:parts.slice(0,index+1).join('/'),children:new Map(),file:index===parts.length-1});
          children=children.get(part).children;
        });
      }
      function renderChildren(children){
        const list=document.createElement('ul');list.className='file-children';
        const ordered=Array.from(children.values()).sort((a,b)=>a.path==='main.cvc'?-1:b.path==='main.cvc'?1:a.file!==b.file?(a.file?1:-1):a.name.localeCompare(b.name));
        for(const node of ordered){
          const item=document.createElement('li');list.append(item);
          const open=!node.file&&foldersForProject().has(node.path);
          const kind=!node.file?'folder':typeof projectFiles[node.path]!=='string'?'binary':node.name.endsWith('.h')?'header':'source';
          const button=treeButton(node.name,kind,open);button.title=node.path;
          button.classList.add(node.file?'project-file':'directory');
          if(node.file&&node.path===currentFile){button.classList.add('active');button.setAttribute('aria-current','true');}
          button.addEventListener('click',()=>{
            if(busy||workspace?.pending)return;
            if(node.file)chooseFile(node.path);
            else{if(open)foldersForProject().delete(node.path);else foldersForProject().add(node.path);renderTree();}
          });item.append(button);
          if(open)item.append(renderChildren(node.children));
        }
        return list;
      }
      nav.append(renderChildren(root));
    }
  }
  function showFile(){
    const value=projectFiles[currentFile];editor.readOnly=typeof value!=='string';
    if(!editor.readOnly){editor.value=value;return;}
    const data=bytes(value.base64),rows=[];
    for(let offset=0;offset<data.length;offset+=16){
      const part=data.slice(offset,offset+16);
      rows.push(offset.toString(16).padStart(6,'0')+'  '+Array.from(part,b=>b.toString(16).padStart(2,'0')).join(' ').padEnd(47)+'  '+Array.from(part,b=>b>=32&&b<127?String.fromCharCode(b):'.').join(''));
    }
    editor.value=rows.join('\n');
  }
  function chooseFile(name){
    if(busy||workspace?.pending)return;persist();currentFile=name;revealFile(name);showFile();
    $('current-name').textContent=(examples.find(p=>p.id===current)?.label||current)+'/'+name;$('file-select').value=name;
    editor.scrollTop=0;editor.scrollLeft=0;updateEditor();renderTree();
  }
  function choose(id,skipPersist=false){
    if(busy||workspace?.pending)return;if(!skipPersist)persist();current=id;const project=examples.find(e=>e.id===id);
    projectFiles={...project.files};
    try{const draft=JSON.parse(localStorage.getItem('cvcc-project-'+id)||'null');
      if(draft){for(const name of Object.keys(projectFiles))if(typeof projectFiles[name]==='string'&&typeof draft[name]==='string')projectFiles[name]=draft[name];}
      if(typeof draft?.['cartridge.json']==='string')projectFiles['cartridge.json']=draft['cartridge.json'];
      if(!draft&&Object.keys(projectFiles).length===1){const legacy=localStorage.getItem('cvcc-draft-'+id);if(legacy!==null)projectFiles['main.cvc']=legacy;}
    }catch{}
    currentFile='main.cvc';closedProjects.delete(current);showFile();
    $('example-select').value=id;$('file-select').replaceChildren(...Object.keys(projectFiles).map(name=>new Option(name,name)));
    $('current-name').textContent=(project.label||id)+'/main.cvc';$('file-select').value=currentFile;
    editor.scrollTop=0;editor.scrollLeft=0;workspace?.select(project);updateEditor();renderTree();
  }
  function updateCartridge(){
    try{
      const config=JSON.parse(projectFiles['cartridge.json']||'{}');
      const profile=cartridgeProfiles.find(p=>p.id===(config.mapper||'sg1000'));
      $('cartridge-mapper').value=profile?.id||'';
      $('cartridge-ram-label').hidden=profile?.id!=='asc16l';
      $('cartridge-ram').value=String(config.ram_kib||16);
      $('cartridge-note').textContent=profile ? (profile.banked?'Codice fisso: 32 KB. Banchi dati da 16 KB configurabili in cartridge.json.':'ROM fino a '+profile.rom_limit/1024+' KB. RAM: '+(profile.ram_end-profile.ram_start)/1024+' KB.')+' La scelta sarà applicata alla prossima compilazione.' : 'Mapper sconosciuto in cartridge.json.';
    }catch{$('cartridge-note').textContent='Correggi cartridge.json prima di cambiare mapper.';}
  }
  function changeCartridge(){
    if(busy||workspace?.pending){updateCartridge();return;}
    persist();
    try{
      const config=JSON.parse(projectFiles['cartridge.json']||'{}');
      const profile=cartridgeProfiles.find(p=>p.id===$('cartridge-mapper').value);
      if(!profile)throw new Error('Scegli un mapper valido.');
      if(!profile.banked&&Object.keys(config.banks||{}).length)throw new Error('Questo progetto usa banchi dati: rimuovi la configurazione banks prima di scegliere un mapper senza banchi.');
      config.mapper=profile.id;
      if(profile.id==='asc16l')config.ram_kib=Number($('cartridge-ram').value);else delete config.ram_kib;
      projectFiles['cartridge.json']=JSON.stringify(config,null,2)+'\n';
      if(currentFile==='cartridge.json')showFile();
      $('file-select').replaceChildren(...Object.keys(projectFiles).map(name=>new Option(name,name)));$('file-select').value=currentFile;
      persist();updateEditor();renderTree();
    }catch(error){updateCartridge();$('cartridge-note').textContent=error.message;}
  }
  $('cartridge-mapper').addEventListener('change',changeCartridge);
  $('cartridge-ram').addEventListener('change',changeCartridge);
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
    $('download-size').textContent=`${item.size.toLocaleString('it-IT')} byte · codice e dati: ${(lastBuild.code_bytes+(lastBuild.bank_data_bytes||0)).toLocaleString('it-IT')} byte`;
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
    if(busy||workspace?.pending)return;busy=true;errorLine=null;persist();
    const files={...projectFiles},source=JSON.stringify(files),name=(examples.find(p=>p.id===current)?.label||current).replace(/[^a-zA-Z0-9_-]/g,'-'),projectId=current;
    $('compile').disabled=true;$('compile-label').textContent='Compilazione…';
    $('build-duration').textContent='BUILD IN CORSO';$('build-dot').className='';$('status-text').textContent='Compilazione sul Mac…';
    outputs.diagnostics='→ Parsing Tree-sitter, controlli CVCC e compilazione della ROM…';output('diagnostics');
    try{
      const response=await fetch('/api/compile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({files})});
      const result=await response.json();
      if(!response.ok){errorLine=result.line||null;errorFile=result.file||null;throw new Error(result.error||'Compilazione non riuscita.');}
      lastBuild={...result,name,projectId};lastSource=source;
      outputs.assembly=result.assembly;
      outputs.diagnostics=`✓ ${result.cartridge.label} · RAM disponibile: ${result.cartridge.ram_end-result.cartridge.ram_start} byte\n✓ Parsing e controlli semantici superati\n✓ ROM assemblata con sjasmplus · ${result.rom_bytes.toLocaleString('it-IT')} byte\n✓ Build completata in ${(result.elapsed_ms/1000).toFixed(2)} s\n\nSHA-256  ${result.sha256}`;
      $('build-duration').textContent=(result.elapsed_ms/1000).toFixed(2)+' s';$('build-dot').className='success';
      $('rom-size').innerHTML=(result.rom_bytes/1024)+'<small>KiB</small>';
      $('code-size').innerHTML=(result.code_bytes+(result.bank_data_bytes||0)).toLocaleString('it-IT')+'<small>byte</small>';
      $('ram-size').innerHTML=result.ram_bytes+'<small>byte</small>';
      exportChoices();
      $('status-text').textContent='Build riuscita · '+name+'.sg';
      try{
        await player.load(bytes(result.rom),result.cartridge);
        $('empty-screen').hidden=true;$('pause-overlay').hidden=true;$('power-led').className='on';
        $('preview-state').textContent='IN ESECUZIONE';$('preview-state').className='preview-state live';
        $('fps').textContent=player.fps.toFixed(2)+' FPS';
        for(const id of ['pause','reset','sound'])$(id).disabled=false;
        $('pause').innerHTML='Ⅱ <span>Pausa</span>';
        $('preview-note').textContent='ROM in esecuzione. Clicca sullo schermo: P1 frecce + Z/X; P2 WASD + F/G. La compilazione resta locale.';
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
    if(event.key==='Tab'&&!editor.readOnly){
      event.preventDefault();const start=editor.selectionStart,end=editor.selectionEnd;
      editor.setRangeText('    ',start,end,'end');persist();updateEditor();
    }
  });
  document.addEventListener('keydown',event=>{if((event.metaKey||event.ctrlKey)&&event.key==='Enter'&&!document.querySelector('dialog[open]')){event.preventDefault();void compile();}});
  $('file-select').addEventListener('change',()=>{if(busy){$('file-select').value=currentFile;return;}chooseFile($('file-select').value);});
  document.querySelectorAll('.output-tab').forEach(b=>b.addEventListener('click',()=>output(b.dataset.tab)));
  $('compile').addEventListener('click',compile);
  $('example-select').addEventListener('change',()=>{if(busy){$('example-select').value=current;return;}choose($('example-select').value);});
  $('goto-error').addEventListener('click',()=>{if(!errorLine)return;if(errorFile&&Object.hasOwn(projectFiles,errorFile))chooseFile(errorFile);const lines=editor.value.split('\n');const start=lines.slice(0,errorLine-1).reduce((sum,line)=>sum+line.length+1,0);editor.focus();editor.setSelectionRange(start,start+(lines[errorLine-1]||'').length);editor.scrollTop=Math.max(0,(errorLine-4)*22);syncScroll();updateCursor();});
  $('save-source').addEventListener('click',()=>saveFile(currentFile.split('/').at(-1),editor.readOnly?bytes(projectFiles[currentFile].base64):editor.value,editor.readOnly?'application/octet-stream':'text/plain'));
  $('save-project').addEventListener('click',async()=>{
    persist();const name=(examples.find(p=>p.id===current)?.label||current).replace(/[^a-zA-Z0-9_-]/g,'-');
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
  workspace=new WorkspaceUI({
    snapshot(){persist();return structuredClone(projectFiles);},
    files(){return projectFiles;},
    exampleFiles(){return examples.find(p=>p.id===current)?.files||{};},
    busy(){return busy;},
    open(project,discard){
      persist();
      if(discard){localStorage.removeItem('cvcc-project-'+project.id);localStorage.removeItem('cvcc-base-'+project.id);}
      const index=examples.findIndex(p=>p.id===project.id);
      if(index<0)examples.push(project);else examples[index]=project;
      $('example-select').replaceChildren(...examples.map(p=>new Option(p.label||p.id,p.id)));
      choose(project.id,true);
    }
  });
  fetch('/api/config').then(async response=>{if(!response.ok)throw new Error('Server non disponibile');return response.json();}).then(config=>{
    examples=config.examples;cartridgeProfiles=config.cartridges;
    $('cartridge-mapper').replaceChildren(...cartridgeProfiles.map(p=>new Option(p.label,p.id)));$('cartridge-mapper').disabled=false;
    $('example-select').replaceChildren(...examples.map(project=>new Option(project.id,project.id)));
    choose('square');$('server-led').className='online';$('connection-label').textContent='LOCALE';$('compile').disabled=false;
    outputs.diagnostics='✓ Compilatore locale pronto.\nAvvio del primo esempio…';output();void compile();
  }).catch(error=>{$('connection-label').textContent='OFFLINE';outputs.diagnostics=error.message;output();});
})();
