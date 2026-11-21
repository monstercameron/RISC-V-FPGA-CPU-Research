"""Compile the tiny RV64I firmware with LLVM; produces binary and BRAM image.
SPDX-License-Identifier: MIT
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--clang',default=shutil.which('clang'))
    p.add_argument('--objcopy',default=shutil.which('llvm-objcopy'))
    p.add_argument('--objdump',default=shutil.which('llvm-objdump'))
    p.add_argument('--source',default='sim/cpu/firmware.c')
    p.add_argument('--out-dir',default='build/cpu/firmware')
    a=p.parse_args()
    if not a.clang or not a.objcopy: p.error('clang and llvm-objcopy required')
    source=(ROOT/a.source).resolve()
    out=(ROOT/a.out_dir).resolve()
    if not source.is_file(): p.error('source must be an existing C file')
    if not out.is_relative_to((ROOT/'build').resolve()):
        p.error('out-dir must be inside the repository build/ directory')
    out.mkdir(parents=True,exist_ok=True)
    elf=out/'firmware.elf'
    binary=out/'firmware.bin'
    command=[a.clang,'--target=riscv64-unknown-elf','-march=rv64i_zifencei',
        '-mabi=lp64','-mcmodel=medany','-msmall-data-limit=0','-mno-relax',
        '-O1','-ffreestanding','-fno-builtin','-fno-stack-protector',
        '-fno-zero-initialized-in-bss','-nostdlib',
        '-Wl,--no-relax','-Wl,-T,'+str(ROOT/'sim/cpu/link.ld'),
        str(ROOT/'sim/cpu/start.S'),str(source),'-o',str(elf)]
    started=time.perf_counter()
    subprocess.run(command,check=True,timeout=120)
    subprocess.run([a.objcopy,'-O','binary',str(elf),str(binary)],check=True)
    payload=binary.read_bytes()
    if len(payload)>8192: raise ValueError('Firmware admission limit exceeded')
    size=len(payload)
    payload=payload.ljust(16384,b'\0')
    (out/'firmware-bram.hex').write_text(''.join(f'{int.from_bytes(payload[i:i+8],"little"):016x}\n' for i in range(0,len(payload),8)),encoding='ascii')
    elapsed=time.perf_counter()-started
    if a.objdump:
        disassembly=subprocess.check_output([a.objdump,'-d',str(elf)],text=True)
        (out/'firmware.disasm.txt').write_text(disassembly,encoding='utf-8')
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    inputs=[source,ROOT/'sim/cpu/start.S',ROOT/'sim/cpu/link.ld']
    report={'compiler':subprocess.check_output([a.clang,'--version'],text=True).splitlines()[0],
        'command':command,'isa':'rv64i_zifencei','abi':'lp64','payload_bytes':size,
        'build_wall_seconds':elapsed,
        'input_sha256':{path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path):sha(path) for path in inputs},
        'artifact_sha256':{name:sha(out/name) for name in ['firmware.elf','firmware.bin','firmware-bram.hex']}}
    (out/'build.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print('Built',binary,'and 2048-word BRAM initialization image.')


if __name__=='__main__': main()
