"""Simulator back ends for the CPU test and benchmark scripts.

test_cpu.py, bench/run_bench.py and bench/lzma_run.py take --sim {icarus,verilator}.
Icarus Verilog is the default and the reference. Verilator is optional and much
faster (110-400x on these testbenches); in the 2026-11-21 cross-checks it gave
traces and counts identical to Icarus.

    sim = simulator.get('verilator')
    exe = sim.build('tb_core', [core, tb], out / 'tb_core.vvp',
                    params={'MEM_BYTES': 65536}, defines=['WIDE_TRACE'])
    output = command([*exe, '+image=...'])      # same plusargs for both

Icarus: iverilog -g2012 -Wall -D<define> -P<top>.<param>=V writes the .vvp the
caller names; the run command is vvp <file>.

Verilator: verilator --cc --exe --main --timing -D<define> -G<param>=V, then make
with -j from the CPU count (at most 4). With clang++ (no g++), make gets
CFG_CXXFLAGS_STD=-std=gnu++20 CFG_CXXFLAGS_COROUTINES=. Each build has its own
folder under build/sim-cache/verilator/<top>-<key>, the key a SHA-256 of the
source contents, top, parameters, defines, Verilator version and C++ compiler, so
repeated runs reuse it. Verilator is found through VERILATOR_ROOT, then PATH,
then the unpacked packages in build/third-party/verilator/root if present.

Verilator is a 2-state simulator: registers and memories start at 0 (unless the
run adds +verilator+rand+reset+2), where Icarus starts them at X. A bug that
depends on reset values can therefore pass under Verilator; Icarus stays the
cross-check for every logged result.

Every step (one compile or one make) stops after 5 minutes.
SPDX-License-Identifier: MIT
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CHOICES = ('icarus', 'verilator')
STEP_TIMEOUT = 300
VENDORED = ROOT / 'build/third-party/verilator/root'
CACHE = ROOT / 'build/sim-cache/verilator'
WARNINGS = ['-Wno-fatal', '-Wno-lint', '-Wno-style', '-Wno-TIMESCALEMOD']
OPT = ['OPT_FAST=-O2', 'OPT_SLOW=-O1', 'OPT_GLOBAL=-O2']


class SimulatorMissing(SystemExit):
    pass


def _run(args, timeout=STEP_TIMEOUT, env=None):
    completed = subprocess.run([str(x) for x in args], capture_output=True, text=True, timeout=timeout, env=env)
    if completed.returncode:
        raise RuntimeError(f'Command failed: {" ".join(map(str, args))}\n{completed.stdout}{completed.stderr}')
    return completed.stdout


class Icarus:
    name = 'icarus'
    label = 'Icarus Verilog'

    def __init__(self):
        if not shutil.which('iverilog') or not shutil.which('vvp'):
            raise SimulatorMissing('iverilog and vvp are required (Ubuntu/WSL: apt install iverilog); '
                                   'on Windows use the documented launchers')

    def version(self):
        return _run(['iverilog', '-V'], 60).splitlines()[0]

    def info(self):
        return {'simulator': self.version(), 'simulator_name': self.name}

    def build(self, top, sources, output, params=None, defines=(), timeout=STEP_TIMEOUT):
        """Compile; returns the command (a list) that runs it, plusargs to follow."""
        _run(['iverilog', '-g2012', '-Wall', *[f'-D{d}' for d in defines], '-s', top,
              *[f'-P{top}.{k}={v}' for k, v in (params or {}).items()], '-o', output, *sources], timeout)
        return ['vvp', Path(output)]

    def elaborate(self, top, sources, output, params=None, defines=(), timeout=STEP_TIMEOUT):
        """Compile-only check of a top that is not run."""
        self.build(top, sources, output, params, defines, timeout)


class Verilator:
    name = 'verilator'
    label = 'Verilator'

    def __init__(self):
        self.env = os.environ.copy()
        root = self.env.get('VERILATOR_ROOT')
        if root and (Path(root) / 'bin/verilator').is_file():
            self.exe = str(Path(root) / 'bin/verilator')
        elif shutil.which('verilator'):
            self.exe = shutil.which('verilator')
        elif (VENDORED / 'usr/bin/verilator').is_file():
            # Ubuntu packages unpacked without root (build/verilator/env.sh does the same).
            self.exe = str(VENDORED / 'usr/bin/verilator')
            self.env['PATH'] = f'{VENDORED / "usr/bin"}{os.pathsep}{self.env.get("PATH", "")}'
            self.env['VERILATOR_ROOT'] = str(VENDORED / 'usr/share/verilator')
            self.env['VERILATOR_BIN'] = '../../../bin/verilator_bin'
            libs = [str(p) for p in sorted((VENDORED / 'usr/lib').glob('*-linux-gnu'))]
            self.env['LD_LIBRARY_PATH'] = os.pathsep.join(libs + [x for x in [self.env.get('LD_LIBRARY_PATH')] if x])
        else:
            raise SimulatorMissing('Verilator not found: set VERILATOR_ROOT, put verilator on PATH, or unpack it '
                                   f'into {VENDORED} (usr/bin/verilator)')
        path = self.env.get('PATH')
        self.make = shutil.which('make', path=path)
        if not self.make:
            raise SimulatorMissing('Verilator needs make on PATH')
        # None: Verilator's own default (g++). Without g++, clang++ with the flags in _make_vars().
        self.cxx = self.env.get('CXX') or (None if shutil.which('g++', path=path) else
                                           'clang++' if shutil.which('clang++', path=path) else '')
        if self.cxx == '':
            raise SimulatorMissing('Verilator needs a C++ compiler: g++ or clang++ (or set CXX)')
        self._version = self._cxx_version = None

    def version(self):
        if self._version is None:
            self._version = _run([self.exe, '--version'], 60, self.env).strip()
        return self._version

    def cxx_version(self):
        if self._cxx_version is None:
            self._cxx_version = _run([self.cxx or 'g++', '--version'], 60, self.env).splitlines()[0]
        return self._cxx_version

    def info(self):
        return {'simulator': self.version(), 'simulator_name': self.name, 'simulator_cxx': self.cxx_version()}

    def _make_vars(self):
        if not self.cxx:
            return []
        extra = ['CFG_CXXFLAGS_STD=-std=gnu++20', 'CFG_CXXFLAGS_COROUTINES='] if 'clang' in Path(self.cxx).name else []
        return [f'CXX={self.cxx}', f'LINK={self.cxx}', *extra]

    def _options(self, top, params, defines):
        return [*WARNINGS, '--top-module', top, *[f'-D{d}' for d in defines],
                *[f'-G{k}={v}' for k, v in (params or {}).items()]]

    def build(self, top, sources, output=None, params=None, defines=(), timeout=STEP_TIMEOUT):
        """Verilate and compile, or reuse a cached build; returns the command (a list) that runs it.
        `output` (the Icarus file name) is ignored: builds live in build/sim-cache/verilator."""
        options = self._options(top, params, defines)
        key = hashlib.sha256(json.dumps({
            'options': options, 'make': self._make_vars() + OPT, 'version': self.version(),
            'cxx': self.cxx_version(), 'sources': [hashlib.sha256(Path(s).read_bytes()).hexdigest() for s in sources],
        }, sort_keys=True).encode()).hexdigest()
        folder = CACHE / f'{top}-{key[:16]}'
        binary = folder / f'V{top}'
        if (folder / 'build.json').is_file() and binary.is_file():
            return [binary]
        CACHE.mkdir(parents=True, exist_ok=True)
        if folder.exists():  # an unfinished earlier build
            shutil.rmtree(folder)
        work = Path(tempfile.mkdtemp(prefix=f'.{top}-', dir=CACHE))
        try:
            _run([self.exe, '--cc', '--exe', '--main', '--timing', *options, '-Mdir', work, *sources], timeout, self.env)
            jobs = max(1, min(4, os.cpu_count() or 1))
            make = [self.make, '-C', work, '-f', f'V{top}.mk', *self._make_vars(), *OPT, f'V{top}']
            try:
                _run([*make, f'-j{jobs}'], timeout, self.env)
            except RuntimeError as failure:
                # clang++ 18 crashed once here while another Verilator build was running
                # (2026-11-21) and passed on the next try; make resumes, so retry once, serially.
                print(f'Verilator build of {top}: make failed, retrying with -j1\n{str(failure)[-2000:]}',
                      file=sys.stderr)
                _run([*make, '-j1'], timeout, self.env)
            (work / 'build.json').write_text(json.dumps({
                'top': top, 'key_sha256': key, 'options': options, 'sources': [str(s) for s in sources],
                'verilator': self.version(), 'cxx': self.cxx_version()}, indent=2) + '\n', encoding='utf-8')
            try:
                work.rename(folder)
            except OSError:  # another run finished the same build first
                if not (folder / 'build.json').is_file():
                    raise
        finally:
            if work.exists():
                shutil.rmtree(work, ignore_errors=True)
        return [binary]

    def elaborate(self, top, sources, output=None, params=None, defines=(), timeout=STEP_TIMEOUT):
        """Compile-only check of a top that is not run (verilator --lint-only)."""
        _run([self.exe, '--lint-only', '--timing', *self._options(top, params, defines), *sources], timeout, self.env)


def get(name):
    """The back end for --sim NAME; exits with a clear message if its tools are missing."""
    return {'icarus': Icarus, 'verilator': Verilator}[name]()


def add_argument(parser):
    parser.add_argument('--sim', choices=CHOICES, default='icarus',
                        help='Simulator: icarus (default, the reference) or verilator (faster, 2-state; '
                             'see sim/cpu/simulator.py)')
