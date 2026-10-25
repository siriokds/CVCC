/* Storage UI: user-owned folders and GitHub, independent of compiler/player. */
class WorkspaceUI {
  constructor(bridge) {
    this.bridge=bridge; this.pending=false; this.active=null; this.stale=false;
    this.$=id=>document.getElementById(id);
    this.dialog=this.$('workspace-dialog');
    this.recents=this.read('cvcc-recents-v1',[]);
    this.$('open-workspace').onclick=()=>this.show('local');
    this.$('close-workspace').onclick=()=>{if(!this.pending)this.dialog.close();};
    this.dialog.addEventListener('cancel',event=>{if(this.pending)event.preventDefault();});
    document.querySelectorAll('[data-storage]').forEach(button=>button.onclick=()=>this.show(button.dataset.storage));
    this.$('write-workspace').onclick=()=>this.save();
    this.$('copy-workspace').onclick=()=>this.show('copy');
    this.$('workspace-changes').onclick=()=>this.changes();
    this.$('open-local').onclick=()=>this.open({kind:'local',path:this.$('workspace-path').value.trim()});
    this.$('open-github').onclick=()=>this.open({kind:'github',repo:this.$('github-repo').value.trim(),branch:this.$('github-branch').value.trim(),folder:this.$('github-folder').value.trim()});
    this.$('open-synced').onclick=()=>this.show('local');
    this.$('pick-workspace').onclick=async()=>{const result=await this.request('pick',{});if(result&&!result.cancelled)this.$('workspace-path').value=result.path;};
    this.$('check-github').onclick=async()=>{const user=await this.request('account',{});if(user)this.$('github-account').textContent='Collegato come '+user.login+' · GitHub CLI su questo Mac';};
    this.$('list-github').onclick=async()=>{
      const result=await this.request('repositories',{});if(!result)return;
      this.repositories=result.repositories;
      const select=this.$('repo-choice');select.replaceChildren(new Option('Scegli tra gli ultimi 100 repository…',''),...result.repositories.map(r=>new Option(r.name,r.name)));
      this.$('repo-choice-label').hidden=false;
    };
    this.$('repo-choice').onchange=()=>{
      const repo=this.repositories.find(r=>r.name===this.$('repo-choice').value);if(!repo)return;
      this.$('github-repo').value=repo.name;this.$('github-branch').value=repo.branch;this.$('github-folder').value='';this.$('folder-choice-label').hidden=true;
    };
    this.$('find-projects').onclick=async()=>{
      const result=await this.request('projects',{repo:this.$('github-repo').value.trim(),branch:this.$('github-branch').value.trim()});if(!result)return;
      this.$('folder-choice').replaceChildren(new Option(result.folders.length?'Scegli il progetto…':'Nessun main.cvc trovato','?'),...result.folders.map(f=>new Option(f||'Radice del repository',f)));
      this.$('folder-choice-label').hidden=false;
    };
    this.$('folder-choice').onchange=()=>{if(this.$('folder-choice').value!=='?')this.$('github-folder').value=this.$('folder-choice').value;};
    this.$('pick-copy-parent').onclick=async()=>{
      const result=await this.request('pick',{});
      if(result&&!result.cancelled)this.$('copy-path').value=result.path.replace(/\/$/,'')+'/NuovoProgetto';
    };
    this.$('create-copy').onclick=async()=>{
      const result=await this.request('create',{path:this.$('copy-path').value.trim(),files:this.bridge.snapshot()});
      if(result)this.accept(result,true);
    };
    this.$('send-commit').onclick=()=>this.commit();
    this.$('reload-workspace').onclick=()=>{
      if(!this.active)return;
      if(!confirm('Aprire la versione salvata e sostituire la bozza di questo progetto? Prima puoi scaricare il progetto ZIP o salvare una copia.'))return;
      this.open(this.active.storage,true);
    };
    document.addEventListener('keydown',event=>{
      if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='s'){
        event.preventDefault();if(!this.pending&&!this.dialog.open)this.save();
      }
    });
    window.addEventListener('beforeunload',event=>{if(this.pending||this.draftFailed){event.preventDefault();event.returnValue='';}});
  }
  read(key,fallback){try{return JSON.parse(localStorage.getItem(key))??fallback;}catch{return fallback;}}
  equal(a,b){const canonical=o=>JSON.stringify(Object.keys(o).sort().map(k=>[k,o[k]]));return canonical(a)===canonical(b);}
  show(mode){
    if(this.pending)return;
    if(this.bridge.busy()){this.$('storage-state').textContent='Attendi il termine della compilazione.';return;}
    this.$('workspace-error').hidden=true;
    this.$('workspace-title').textContent=mode==='copy'?'Salva una copia':mode==='changes'?'Modifiche del progetto':'Apri progetto';
    for(const key of ['local','github','cloud','copy','changes'])this.$(key+'-fields').hidden=key!==mode;
    document.querySelector('.storage-tabs').hidden=['copy','changes'].includes(mode);
    document.querySelectorAll('[data-storage]').forEach(b=>b.classList.toggle('selected',b.dataset.storage===mode));
    this.$('recent-section').hidden=['copy','changes'].includes(mode);
    this.renderRecents();if(!this.dialog.open)this.dialog.showModal();
  }
  renderRecents(){
    const list=this.$('recent-workspaces');list.replaceChildren();
    if(!this.recents.length){list.textContent='I progetti aperti compariranno qui.';return;}
    for(const entry of this.recents){
      const button=document.createElement('button');button.className='recent-project';
      const label=document.createElement('strong');label.textContent=entry.label;
      const location=document.createElement('small');location.textContent=(entry.kind==='github'?'GitHub · ':'Computer · ')+entry.path;
      button.append(label,location);button.onclick=()=>this.open(entry);list.append(button);
    }
  }
  async request(action,payload){
    if(this.pending||this.bridge.busy())return null;
    this.pending=true;this.$('workspace-error').hidden=true;
    this.$('storage-state').textContent='Operazione in corso…';
    const buttons=[...this.dialog.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
    try{
      const response=await fetch('/api/workspace/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const result=await response.json();if(!response.ok)throw new Error(result.error||'Operazione non riuscita.');
      return result;
    }catch(error){
      this.$('workspace-error').textContent=error.message;this.$('workspace-error').hidden=false;
      if(!this.dialog.open)this.dialog.showModal();
      return null;
    }finally{this.pending=false;buttons.forEach(b=>b.disabled=false);this.changed();if(!this.$('changes-fields').hidden)this.renderChanges();}
  }
  async open(descriptor,discard=false){
    const result=await this.request('open',descriptor);if(result)this.accept(result,discard);
  }
  accept(project,discard=false){
    this.bridge.open(project,discard);this.dialog.close();
    this.recents=[project.storage,...this.recents.filter(r=>JSON.stringify(r)!==JSON.stringify(project.storage))].slice(0,12);
    try{localStorage.setItem('cvcc-recents-v1',JSON.stringify(this.recents));}catch{}
  }
  select(project){
    this.active=project.storage?project:null;
    this.stale=false;
    if(this.active){
      const base=this.read('cvcc-base-'+project.id,null);
      const files=this.bridge.files();
      this.stale=!!base&&base!==project.revision&&!this.equal(files,project.files);
    }
    this.changed();
  }
  changed(draftOK){
    if(draftOK!==undefined)this.draftFailed=!draftOK;
    const files=this.bridge.files(), project=this.active;
    let state=this.draftFailed?'Bozza non salvata: spazio browser esaurito. Scarica una copia.':'Bozza nel browser';
    if(project){
      const dirty=!this.equal(files,project.files);
      this.$('storage-location').textContent=(project.storage.kind==='github'?'GitHub · ':'Computer · ')+project.storage.path;
      if(!this.draftFailed)state=this.stale?'Versione salvata cambiata · verifica la bozza':dirty?(project.storage.kind==='github'?'Bozza nel browser · da inviare a GitHub':'Modifiche da salvare su disco'):(project.storage.kind==='github'?'Allineato al commit '+project.revision.slice(0,7):'Salvato su disco');
      if(!this.stale){try{localStorage.setItem('cvcc-base-'+project.id,JSON.stringify(project.revision));}catch{}}
    }else this.$('storage-location').textContent='Esempio · salva una copia per creare il tuo progetto';
    this.$('storage-state').textContent=state;
    this.$('storage-state').classList.toggle('storage-warning',this.stale||this.draftFailed);
    this.$('write-workspace').textContent=project?.storage.kind==='github'?'Salva bozza':'Salva';
  }
  async save(){
    if(this.pending||this.bridge.busy())return;
    const files=this.bridge.snapshot();
    if(!this.active){this.show('copy');return;}
    if(this.active.storage.kind==='github'){this.changed();return;}
    if(this.stale){this.changes();this.$('workspace-error').textContent='La cartella è cambiata dalla creazione della bozza. Salva una copia oppure apri la versione salvata.';this.$('workspace-error').hidden=false;return;}
    this.show('changes');this.renderChanges();
    const result=await this.request('save',{id:this.active.id,revision:this.active.revision,files});
    if(result){Object.assign(this.active,result);this.stale=false;this.changed();this.dialog.close();}
  }
  changes(){this.bridge.snapshot();this.show('changes');this.renderChanges();}
  renderChanges(){
    const project=this.active,files=this.bridge.files(),base=project?.files||this.bridge.exampleFiles();
    this.$('changes-location').textContent=project?project.storage.path:'Esempio: salva una copia per creare un progetto personale.';
    const list=this.$('changes-list');list.replaceChildren();let count=0;
    for(const name of Object.keys(files)){
      if(this.equal({file:files[name]},{file:base[name]}))continue;
      count++;const detail=document.createElement('details'),summary=document.createElement('summary');summary.textContent=(name in base?'M  ':'A  ')+name;detail.append(summary);
      if(typeof files[name]==='string'){
        const columns=document.createElement('div');columns.className='compare-files';
        for(const [title,value] of [['Salvato',base[name]||''],['La tua bozza',files[name]]]){
          const section=document.createElement('section'),heading=document.createElement('strong'),pre=document.createElement('pre');heading.textContent=title;pre.textContent=value;section.append(heading,pre);columns.append(section);
        }detail.append(columns);
      }else{const p=document.createElement('p');p.textContent='Dati binari modificati';detail.append(p);}
      list.append(detail);
    }
    if(!count)list.textContent='Nessuna modifica rispetto alla versione aperta.';
    const github=project?.storage.kind==='github';
    this.$('commit-label').hidden=!github;this.$('send-commit').hidden=!github;
    this.$('send-commit').disabled=!count||this.stale;
    this.$('reload-workspace').hidden=!project;
    this.$('changes-help').textContent=github?'Commit sul branch '+project.storage.branch+'. Se il branch cambia, l’invio viene fermato.':'⌘S salva il progetto su disco. Le modifiche esterne vengono controllate prima di scrivere.';
  }
  async commit(){
    if(!this.active||this.stale||this.pending)return;
    const result=await this.request('commit',{id:this.active.id,revision:this.active.revision,files:this.bridge.snapshot(),message:this.$('commit-message').value});
    if(result){Object.assign(this.active,result);this.changed();this.$('commit-message').value='';this.dialog.close();}
  }
}
