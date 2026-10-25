// Exercise the actual WebAssembly emulator ABI without a browser or network.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const createCore = require(process.argv[2]);
(async () => {
  const core = await createCore({print:()=>{}, printErr:()=>{}});
  core._web_init();
  const cases = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
  let pass, fail, alternate;
  for (const item of cases) {
    const rom = fs.readFileSync(item.path), ptr = core._malloc(rom.length);
    try {
      core.HEAPU8.set(rom, ptr);
      core._web_set_mapper(item.mapper);
      core._web_set_asc16l_ram(item.ram);
      assert.equal(core._web_load(ptr, rom.length), 1, item.label+' load');
    } finally { core._free(ptr); }
    for (let reset=0; reset<2; reset++) {
      if (reset) core._web_reset();
      for (let frame=0; frame<180; frame++) core._web_run();
      const pixels = new Uint16Array(core.HEAPU8.buffer, core._web_pixels(), core._web_width()*core._web_height());
      assert.equal(new Set(pixels).size, 1, item.label+' solid diagnostic frame');
      if (item.label==='color2') pass=pixels[0];
      else if (item.label==='color4') alternate=pixels[0];
      else if (item.label==='color6') { fail=pixels[0];assert.notEqual(fail,pass); }
      else if(item.heartbeat) {
        const seen=new Set();
        for(let frame=0;frame<8;frame++) {
          core._web_run();
          const pixel=new Uint16Array(core.HEAPU8.buffer,core._web_pixels(),1)[0];
          assert.ok(pixel===pass || pixel===alternate,item.label+' banked call diagnostic');
          seen.add(pixel);
        }
        assert.equal(seen.size,2,item.label+' must keep returning and processing VBlank');
      } else assert.equal(pixels[0],pass,item.label+' RAM/bank/VRAM diagnostic, reset '+reset);
    }
    console.log('PASS',item.label);
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
