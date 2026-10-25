/* CVCC player adapter. Uses the external GearSC3000 Web ABI; no core is bundled. */
class CartridgePlayer {
  constructor(canvas) {
    this.canvas = canvas;
    this.context = canvas.getContext('2d', {alpha:false});
    this.running = false;
    this.paused = false;
    this.muted = true;
    this.held = new Set();
    this.keys = new Map([['ArrowUp',4],['ArrowDown',5],['ArrowLeft',6],['ArrowRight',7],['KeyZ',0],['KeyX',8],['KeyW',20],['KeyS',21],['KeyA',22],['KeyD',23],['KeyF',16],['KeyG',24]]);
    this.audioTime = 0;
    this.nodes = new Set();
    this.ready = typeof createGearSC3000 === 'function' ? createGearSC3000({locateFile:name=>'/player/'+name}).then(core=>{this.core=core;core._web_init();return this;}) : Promise.reject(new Error('Player Web non disponibile: indica la cartella dist di GearSC3000.'));
    this.ready.catch(()=>{});
    canvas.addEventListener('keydown',event=>{
      if (!this.running || this.paused || event.metaKey || event.ctrlKey || !this.keys.has(event.code)) return;
      event.preventDefault(); this.held.add(event.code); this.updatePad();
    });
    canvas.addEventListener('keyup',event=>{if(this.keys.has(event.code)){event.preventDefault();this.held.delete(event.code);this.updatePad();}});
    canvas.addEventListener('blur',()=>this.releaseKeys());
    window.addEventListener('blur',()=>this.releaseKeys());
    document.addEventListener('visibilitychange',()=>{this.lastTime=0;this.debt=0;if(document.hidden){this.releaseKeys();this.flushAudio();}});
    requestAnimationFrame(time=>this.tick(time));
  }
  releaseKeys(){this.held.clear();this.updatePad();}
  updatePad(){const masks=[0,0];for(const key of this.held){const code=this.keys.get(key);masks[code>>4]|=1<<(code&15);}for(let port=0;port<2;port++)this.core?._web_pad(port,masks[port]);}
  flushAudio(){for(const node of this.nodes){try{node.stop();}catch{}}this.nodes.clear();this.audioTime=0;}
  async load(bytes){
    await this.ready;
    this.running=false; this.flushAudio(); this.releaseKeys();
    const core=this.core, ptr=core._malloc(bytes.length);
    if(!ptr)throw new Error('Memoria insufficiente nel player.');
    let ok;
    try{
      core.HEAPU8.set(bytes,ptr);
      core._web_set_mapper(7); // ABI index: SG-1000 1 KiB cartridge.
      core._web_set_timing(1); // NTSC.
      core._web_set_borders(0);
      ok=core._web_load(ptr,bytes.length);
    }finally{core._free(ptr);}
    if(!ok)throw new Error('Il player non ha accettato la ROM.');
    // Align the core clock before the first frame (the ABI resets the machine).
    // Older external player builds retain their native timing.
    const aligned=typeof core._web_set_target_fps==='function' ? core._web_set_target_fps(60) : 0;
    this.fps=Number.isFinite(aligned)&&aligned>1 ? aligned : core._web_fps();
    this.paused=false;this.running=true;this.lastTime=0;this.debt=0;
  }
  pause(){this.paused=!this.paused;this.releaseKeys();this.flushAudio();this.lastTime=0;this.debt=0;return this.paused;}
  reset(){this.core._web_reset();this.flushAudio();this.lastTime=0;this.debt=0;this.releaseKeys();}
  async sound(){
    if(!this.audio)this.audio=new AudioContext();
    await this.audio.resume();
    this.muted=!this.muted;this.flushAudio();return !this.muted;
  }
  playAudio(){
    if(this.muted||!this.audio||this.audio.state!=='running')return;
    const count=this.core._web_audio_frames();if(!count)return;
    const samples=new Int16Array(this.core.HEAPU8.buffer,this.core._web_audio(),count*2);
    const buffer=this.audio.createBuffer(2,count,48000);
    for(let channel=0;channel<2;channel++){
      const dest=buffer.getChannelData(channel);
      for(let i=0;i<count;i++)dest[i]=samples[i*2+channel]/32768;
    }
    const node=this.audio.createBufferSource();node.buffer=buffer;node.connect(this.audio.destination);
    if(this.audioTime<this.audio.currentTime||this.audioTime>this.audio.currentTime+.25)this.audioTime=this.audio.currentTime+.08;
    node.start(this.audioTime);this.audioTime+=count/48000;this.nodes.add(node);node.onended=()=>this.nodes.delete(node);
  }
  draw(){
    const width=this.core._web_width(),height=this.core._web_height();if(!width||!height)return;
    if(!this.frame||this.frame.width!==width||this.frame.height!==height){this.canvas.width=width;this.canvas.height=height;this.frame=this.context.createImageData(width,height);}
    const raw=new Uint16Array(this.core.HEAPU8.buffer,this.core._web_pixels(),width*height), pixels=this.frame.data;
    for(let i=0;i<raw.length;i++){
      const color=raw[i],j=i*4;
      pixels[j]=((color>>11)&31)*255/31;pixels[j+1]=((color>>5)&63)*255/63;pixels[j+2]=(color&31)*255/31;pixels[j+3]=255;
    }
    this.context.putImageData(this.frame,0,0);
  }
  tick(time){
    if(this.running&&!this.paused&&!document.hidden){
      this.debt=Math.min((this.debt||0)+(this.lastTime?time-this.lastTime:0),150);
      const interval=1000/this.fps;let advanced=false;
      while(this.debt>=interval){this.core._web_run();this.playAudio();this.debt-=interval;advanced=true;}
      if(advanced)this.draw();
    }
    this.lastTime=time;requestAnimationFrame(next=>this.tick(next));
  }
}
window.CartridgePlayer=CartridgePlayer;
