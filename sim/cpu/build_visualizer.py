"""Capture the C demo's real RTL clocks and build the offline HTML viewer.

Windows: python -B sim/cpu/build_visualizer.py (installed LLVM + Ubuntu WSL).
Linux: add --clang/--objcopy/--objdump if those tools are not on PATH.
SPDX-License-Identifier: MIT
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

from reference import execute
from program_catalog import PROGRAMS, public_catalog
from program_inputs import defaults, validate_inputs, expected_output, render_source, display_details, SCHEMAS

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'build/cpu/visualizer'
SOURCES=['rtl/cpu/rv64_core.sv','rtl/cpu/rv64_bram_soc.sv',
         'sim/cpu/start.S','sim/cpu/link.ld','sim/cpu/tb_visualizer.sv',
         'sim/cpu/build_firmware.py','sim/cpu/reference.py','sim/cpu/run_c_demo.py',
         'sim/cpu/build_visualizer.py','sim/cpu/program_catalog.py','sim/cpu/program_inputs.py']

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(args):
    process=subprocess.run([str(x) for x in args],cwd=ROOT,capture_output=True,text=True,timeout=180)
    if process.returncode:
        raise RuntimeError(process.stdout+process.stderr)
    return process.stdout

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for tool in ['clang','objcopy','objdump']:
        name='clang' if tool=='clang' else 'llvm-'+tool
        parser.add_argument('--'+tool,default=shutil.which(name) or
            str(Path(r'C:\Program Files\LLVM\bin')/(name+'.exe')))
    parser.add_argument('--distribution',default='Ubuntu-24.04')
    parser.add_argument('--program',choices=list(PROGRAMS),default='demo')
    parser.add_argument('--inputs-json',type=Path,help='JSON object of the selected program input values')
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--capture-only',action='store_true')
    group.add_argument('--reuse-capture',action='store_true')
    args=parser.parse_args()
    inputs=validate_inputs(args.program,json.loads(args.inputs_json.read_bytes()) if args.inputs_json else None)
    custom=inputs!=defaults(args.program)
    spec=display_details(args.program,inputs,PROGRAMS[args.program])
    source_path=spec['source']
    source_name=Path(source_path).name
    source=render_source(args.program,(ROOT/source_path).read_text(encoding='utf-8'),inputs)
    expected=expected_output(args.program,inputs)
    labels,formats=zip(*spec['outputs'])
    OUT.mkdir(parents=True,exist_ok=True)
    generated=OUT/source_name
    generated_digest=hashlib.sha256(source.encode()).hexdigest()
    hashes={name:sha(ROOT/name) for name in SOURCES+[source_path]}
    if args.reuse_capture:
        saved=json.loads((OUT/'capture-identity.json').read_bytes())
        if saved.get('inputs')!=inputs or saved.get('generated_source_sha256')!=generated_digest:
            raise RuntimeError('Capture inputs changed; rerun without --reuse-capture')
        if saved['sources']!=hashes:
            raise RuntimeError('Capture sources changed; rerun without --reuse-capture')
        for name,digest in saved['artifacts'].items():
            if sha(OUT/name)!=digest: raise RuntimeError('Capture artifact changed: '+name)
    else:
        generated.write_bytes(source.encode())
        (OUT/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n',encoding='utf-8',newline='\n')
        print(run([sys.executable,'-B','sim/cpu/build_firmware.py','--source',generated.relative_to(ROOT),
            '--out-dir','build/cpu/visualizer','--clang',args.clang,'--objcopy',args.objcopy,'--objdump',args.objdump]).strip())
        build=json.loads((OUT/'build.json').read_bytes())
        debug_command=build['command'][:]
        debug_command.insert(1,'-g')
        debug_command[-1]=str(OUT/'firmware-debug.elf')
        run(debug_command)
        run([args.objcopy,'-O','binary',OUT/'firmware-debug.elf',OUT/'firmware-debug.bin'])
        if (OUT/'firmware-debug.bin').read_bytes()!=(OUT/'firmware.bin').read_bytes():
            raise AssertionError('Debug information changed executable bytes')
        disassembly=run([args.objdump,'-d','-l',OUT/'firmware-debug.elf'])
        (OUT/'debug.disasm.txt').write_bytes(disassembly.encode())
        prefix=[]
        if os.name=='nt':
            linux_root=run(['wsl','-d',args.distribution,'--exec','wslpath','-u',ROOT]).strip()
            prefix=['wsl','-d',args.distribution,'--cd',linux_root,'--exec']
        run(prefix+['iverilog','-g2012','-Wall','-s','tb_visualizer','-o','build/cpu/visualizer/capture.vvp',
            'rtl/cpu/rv64_core.sv','rtl/cpu/rv64_bram_soc.sv','sim/cpu/tb_visualizer.sv'])
        print(run(prefix+['vvp','build/cpu/visualizer/capture.vvp',
            '+image=build/cpu/visualizer/firmware-bram.hex','+trace=build/cpu/visualizer/clocks.trace']).strip())
        names=['firmware.bin','firmware-bram.hex','firmware-debug.bin','debug.disasm.txt','clocks.trace','build.json','inputs.json',source_name]
        saved={'sources':hashes,'inputs':inputs,'generated_source_sha256':generated_digest,'artifacts':{name:sha(OUT/name) for name in names}}
        (OUT/'capture-identity.json').write_bytes((json.dumps(saved,indent=2)+'\n').encode())

    payload=(OUT/'firmware.bin').read_bytes()
    image=payload.ljust(16384,b'\0')
    expected_trace,coverage=execute(image,max_steps=100000)
    memory=bytearray(image)
    registers=[0]*32
    actual_trace=[]
    values=['0'];pool={0:0}
    def value_id(value):
        if value not in pool:
            pool[value]=len(values); values.append(f'{value:x}')
        return pool[value]
    assembly={};source_line=0
    for line in (OUT/'debug.disasm.txt').read_text(encoding='utf-8').splitlines():
        mark=re.search('('+re.escape(source_name)+r'|start\.S):(\d+)',line)
        if mark: source_line=int(mark[2]) if mark[1]==source_name else 0
        match=re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.*)$',line)
        if match:
            address=int(match[1],16)
            assembly[address]=[re.sub(r'\s+',' ',match[3]).strip(),source_line,match[2]]
    frames=[];retirements=[];writes=0
    for line in (OUT/'clocks.trace').read_text().splitlines():
        raw=line.split()
        if len(raw)!=30: raise AssertionError('Malformed clock capture')
        cycle=int(raw[0]); x=[int(field,16) for field in raw[1:]]
        (state,pc,insn,a,b,result,ea,flags,addr,wd,rdata,strobe,after,after_pc,retired,rpc,rinsn,rd,rval,npc,
         trapped,cause,tval,retired2,rpc2,rinsn2,rd2,rval2,npc2)=x
        if cycle!=len(frames)+1: raise AssertionError('Non-contiguous clocks')
        if pc not in assembly: raise AssertionError('Missing instruction disassembly')
        if state in (1,2) and int(assembly[pc][2],16)!=insn: raise AssertionError('Instruction mismatch')
        if flags&16:
            writes+=1
            if addr+8>len(memory): raise AssertionError('Out-of-bounds RAM write')
            actual_trace.append(f'W {addr:016x} {wd:016x} {strobe:02x}')
            for lane in range(8):
                if strobe & (1<<lane): memory[addr+lane]=(wd>>(8*lane))&255
        retirement=-1
        if retired:
            actual_trace.append(f'R {rpc:016x} {rinsn:08x} {rd:02x} {rval:016x} {npc:016x}')
            retirement=len(retirements)
            retirements.append([cycle,rd,value_id(rval),rpc,npc])
            if rd: registers[rd]=rval
        # Second retirement slot (architecture 0.5.0): same clock, next in program order.
        retirement2=-1
        if retired2:
            actual_trace.append(f'R {rpc2:016x} {rinsn2:08x} {rd2:02x} {rval2:016x} {npc2:016x}')
            retirement2=len(retirements)
            retirements.append([cycle,rd2,value_id(rval2),rpc2,npc2])
            if rd2: registers[rd2]=rval2
        if trapped:
            flags|=32
            actual_trace.append(f'T {pc:016x} {cause:016x} {tval:016x}')
        frames.append([state,pc,flags,addr,value_id(wd),value_id(rdata),strobe,after,after_pc,
                       value_id(a),value_id(b),value_id(result),value_id(ea),retirement,retirement2])
    if actual_trace!=expected_trace: raise AssertionError('Captured events differ from sequential ISA reference')
    observed=[int.from_bytes(memory[0x3000+i*8:0x3008+i*8],'little') for i in range(len(expected))]
    if observed!=expected or registers[10]!=0 or not frames[-1][2]&32:
        raise AssertionError('C output or completion did not pass')
    if sum(bool(frame[2]&32) for frame in frames)!=1: raise AssertionError('Expected one terminal trap')
    # Chapter labels follow compiler-attributed C lines, not invented stage timings.
    def source_location(fragment):
        return next(i+1 for i,line in enumerate(source.splitlines()) if fragment in line)
    chapters=[{'name':'Startup','frame':0}]
    unavailable=[]
    if args.program=='demo':
        markers=[('Copy inputs',source_location('for (unsigned i = 0; i < 16; ++i)')),
                 ('Sort numbers',source_location('for (unsigned i = 1; i < 16; ++i)')),
                 ('Sum & fingerprint',source_location('i64 sum = 0;')),
                 ('Fibonacci',source_location('u64 a = 0, b = 1;')),
                 ('CRC32',source_location('u32 crc = ~0u;')),
                 ('Check results',source_location('if (sum != ')),
                 ('Write output',source_location('volatile u64 *result'))]
        for i,(name,lo) in enumerate(markers):
            hi=markers[i+1][1] if i+1<len(markers) else 10000
            found=next((j for j,f in enumerate(frames) if f[0]==1 and lo<=assembly[f[1]][1]<hi),None)
            if found is None:
                if not custom: raise AssertionError('Missing chapter: '+name)
                unavailable.append(name)
                continue
            chapters.append({'name':name,'frame':found})
    # Study stops come from executed opcodes/bus events, never estimated timings.
    branch_groups={};loads=[];calls=[];returns=[];stack_writes=[];data_writes=[];outputs=[]
    for j,f in enumerate(frames):
        word=int(assembly[f[1]][2],16);op=word&127
        if f[13]>=0:
            if op==0x63: branch_groups.setdefault(f[1],[]).append((j,f,word))
            if op==3: loads.append(j)
            if op in (0x6f,0x67) and (word>>7)&31==1 and f[1]>0x10: calls.append(j)
            if word==0x00008067: returns.append(j)
        if f[2]&16:
            if 0x3000<=f[3]<0x3000+len(expected)*8: outputs.append(j)
            elif f[3]>=0x3800: stack_writes.append(j)
            else: data_writes.append(j)
    signed_group=next((group for group in branch_groups.values()
        if (group[0][2]>>12)&7 in (4,5)
        and any(f[8]!=f[1]+4 for _,f,_ in group)
        and any(f[8]==f[1]+4 for _,f,_ in group)),[])
    if not signed_group:
        signed_group=next((g for g in branch_groups.values() if (g[0][2]>>12)&7 in (4,5)),[])
    loop_group=next((group for group in branch_groups.values()
        if any(f[8]<f[1] for _,f,_ in group)
        and any(f[8]==f[1]+4 for _,f,_ in group)),[])
    repeated_calls=[j for j in calls if sum(frames[k][1]==frames[j][1] for k in calls)>1]
    picks={
        'load':('First data load',loads[:1]),
        'nextLoad':('Load the next address',[j for j in loads if frames[j][3]!=frames[loads[0]][3]][:1] if loads else []),
        'decisionTaken':('Decision: branch taken',[j for j,f,_ in signed_group if f[8]!=f[1]+4][:1]),
        'decisionNotTaken':('Decision: branch not taken',[j for j,f,_ in signed_group if f[8]==f[1]+4][:1]),
        'backward':('Loop: go around again',[j for j,f,_ in loop_group if f[8]<f[1]][:1]),
        'loopExit':('Loop: final exit',[j for j,f,_ in loop_group if f[8]==f[1]+4][-1:]),
        'stackWrite':('Save a value on the stack',stack_writes[:1]),
        'call':('Call the function',calls[:1]),
        'recursiveCall':('A recursive call',repeated_calls[1:2]),
        'return':('Return to the caller',returns[:1]),
        'dataWrite':('Move an array element',data_writes[:1]),
        'output':('First output write',outputs[:1]),
    }
    study_events={}
    for key in spec['stops']:
        name,matches=picks[key]
        if not matches:
            if not custom: raise AssertionError('Required study behavior missing: '+key)
            unavailable.append(name)
            continue
        j=matches[0]
        chapters.append({'name':name,'frame':j})
        study_events[key]={'clock':j+1,'pc':frames[j][1],'next_pc':frames[j][8],
                          'assembly':assembly[frames[j][1]][0]}
    chapters.append({'name':'Finished: inspect output','frame':len(frames)-1})
    report={'status':'PASS','timestamp_utc':datetime.now(timezone.utc).isoformat(),
        'program':args.program,'source':source_path,'observed_output':observed,
        'inputs':inputs,'custom_inputs':custom,'generated_source_sha256':generated_digest,
        'unavailable_stops':unavailable,
        'study_events':study_events,'calls':len(calls),'stack_writes':len(stack_writes),
        'cycles':len(frames),'retired_instructions':len(retirements),'ram_writes':writes,
        'differential_events':len(actual_trace),'all_outputs_match':True,
        'debug_binary_identical':True,'source_sha256':hashes,
        'firmware_sha256':sha(OUT/'firmware.bin'),'clock_trace_sha256':sha(OUT/'clocks.trace'),
        'scope':'Replay of sampled RTL simulation clocks with synchronous RAM. Not a live FPGA or in-browser RTL simulator.',
        'sampling':'Circuit state, operands and bus before rising edge; RAM and register effects after that edge. '
                   'RAM writes on adapter acceptance, one cycle before CPU acknowledgement. '
                   'C lines are optimized compiler debug attribution, not exact source-level stepping.'}
    add_event=None
    if args.program=='add':
        for index,frame in enumerate(frames):
            word=int(assembly[frame[1]][2],16)
            if frame[0]==1 and word&0xfe00707f==0x33 and frame[13]>=0:
                event=retirements[frame[13]]
                if sorted([int(values[frame[9]],16),int(values[frame[10]],16)])==sorted([inputs['left'],inputs['right']]) and int(values[event[2]],16)==expected[0]:
                    add_event={'clock':index+1,'pc':frame[1],'instruction_hex':f'{word:08x}',
                               'bits':f'{word:032b}','assembly':assembly[frame[1]][0],
                               'rs1':(word>>15)&31,'rs2':(word>>20)&31,'rd':event[1],
                               'operands':[int(values[frame[9]],16),int(values[frame[10]],16)],'result':expected[0]}
                    break
        if add_event is None: raise AssertionError('No actual ADD of the configured inputs retired with the expected result')
        report['addition']=add_event
        chapters.insert(2,{'name':'The ADD instruction','frame':add_event['clock']-1})
    chapters.sort(key=lambda chapter:chapter['frame'])
    data={'meta':report,'values':values,'frames':frames,'retirements':retirements,
          'assembly':assembly,'source':source,'initialBytes':list(payload),'chapters':chapters,
          'programId':args.program,'programTitle':spec['title'],'catalog':public_catalog(),
          'inputs':inputs,'inputSchema':SCHEMAS[args.program],'lesson':spec,
          'outputs':[{'label':label,'format':fmt,'address':0x3000+i*8} for i,(label,fmt) in enumerate(zip(labels,formats))],
          'expected':[f'{v:x}' for v in expected]}
    bit_listing='Address   Instruction bits (31..0)           Hex       Assembly\n'
    bit_listing+='\n'.join(f'0x{pc:04x}    {int(entry[2],16):032b}  {entry[2]}  {entry[0]}' for pc,entry in sorted(assembly.items()))+'\n'
    (OUT/'firmware.bits.txt').write_bytes(bit_listing.encode())
    (OUT/'viewer-data.json').write_bytes(json.dumps(data,separators=(',',':')).encode())
    (OUT/'verification.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())
    archive=ROOT/'build/cpu/programs'/args.program
    archive.mkdir(parents=True,exist_ok=True)
    for name in ('viewer-data.json','verification.json','firmware.bin','firmware.elf',
                 'firmware.disasm.txt','firmware.bits.txt','clocks.trace','build.json','capture-identity.json','inputs.json'):
        shutil.copy2(OUT/name,archive/name)
    shutil.copy2(generated,archive/'program.c')
    print(f'PASS {len(frames):,} clocks; {len(retirements):,} instructions; {len(actual_trace):,} reference events match.')
    if args.capture_only: return
    template=(ROOT/'cpu/visualizer.template.html').read_text(encoding='utf-8')
    if template.count('__CPU_CAPTURE_JSON__')!=1: raise AssertionError('Missing data insertion point')
    encoded=json.dumps(data,separators=(',',':')).replace('<','\\u003c')
    html=template.replace('__CPU_CAPTURE_JSON__',encoded)
    (ROOT/'cpu/cpu-visualizer.html').write_bytes(html.encode())
    report['viewer_sha256']=sha(ROOT/'cpu/cpu-visualizer.html')
    report['template_sha256']=sha(ROOT/'cpu/visualizer.template.html')
    report['html_bytes']=(ROOT/'cpu/cpu-visualizer.html').stat().st_size
    (ROOT/'cpu/visualizer-verification.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print('Built cpu/cpu-visualizer.html (offline, with embedded capture).')

if __name__=='__main__': main()
