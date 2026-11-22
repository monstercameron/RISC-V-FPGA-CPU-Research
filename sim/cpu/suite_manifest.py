"""The suites that sim/cpu/suite.py runs: a declarative table of named steps.

Each step wraps an existing entry point with its own command line unchanged
(test_cpu.py, bench/run_bench.py, check_bitmanip.py, ...). This file only says
which commands make up which suite; suite.py runs them, checks their output and
reports. A step belongs to one or more suites and carries tags for --only/--skip.

To add a suite: add it to SUITES and give it a generator in GENERATORS.
To add a benchmark (for example run_bench.py --benchmark mm): add a BENCH_RUNS entry.
It is used as soon as run_bench.py and build_bench.py accept that --benchmark name;
until then the step is listed as unavailable. A new output format needs a parser in
suite.py PARSERS ('bench' accepts any runner that prints PASS lines and
"<name>: N clocks" lines).

Rules every step obeys (suite.py --self-test checks them):
- one invocation stops after 300 s (AGENTS.md); work that cannot fit is split:
  test_cpu.py --shard K/N plus --merge-shards, run_bench.py --pieces A:B plus merge;
- a step passes only if its parser finds a positive pass count or result line.
SPDX-License-Identifier: MIT
"""
from dataclasses import dataclass, field

STEP_LIMIT = 300        # seconds per invocation; never raised for a step

SUITES = {
    'unit': 'Golden models and harness self-checks: fp_cases.py, test_program_inputs.py, suite.py --self-test',
    'isa': 'test_cpu.py per core and cache size: generated programs, traces against reference.py',
    'fpu': 'test_cpu.py --fpu (ooo core) per cache size; only when the core defines RV64_OOO_FPU',
    'vector': 'test_cpu.py --vector per cache size; only once test_cpu.py has --vector',
    'bitmanip': 'check_bitmanip.py: the B build against the base build, Icarus, released RTL files',
    'bench-smoke': 'Dhrystone ref/fast and LZMA d12 at 64 KiB and 4 KiB L1s (plus --fpu variants when the '
                   'core has RV64_OOO_FPU): the release identity clocks',
    'bench': 'dhrystone, lzma, rt, js (9 pieces + merge), mm, ternary on the timing bench; each needs its build inputs (rt-data, js-ref, mm-data)',
    'icarus-full': "Icarus: test_cpu ooo (6 shards), ooo with 2-beat caches (12 shards), check_bitmanip, "
                   "multicycle, pipe; today's build/cpu/ooo-debug/full_check.sh",
    'soc': 'check_soc_memory.py (SoC memory-model directed checks) and check_btb_reach.py',
    'riscv-tests': 'Official riscv-tests ISA tests (rv64ui/um/uzba/uzbb/uzbs, and rv64uf/ud with the F and D option) '
                   'built with the MIT lab environment, run on reference.py, rv_iss and all three cores; '
                   'needs sim/cpu/fetch_riscv_tests.sh once',
    'negative': 'Negative control: a mutated copy of the core must FAIL test_cpu with a trace mismatch',
    'repo': 'scripts/check_repo.py and scripts/build_site.py (rewrites docs/)',
    'spike-lockstep': 'RTL retirement traces of all three cores against Spike --log-commits (sim/cpu/spike_lockstep.py): '
                      'riscv-tests user set, Dhrystone and LZMA d12 whole, rt and js checkpoint pieces, and a mutated '
                      'core that must be caught; the C2 external-model gate for user mode. Needs Spike '
                      '(sim/cpu/sys/build_spike.sh)',
    'sys': 'rv_iss --sys (cpu/PRIV-CONTRACT.md draft): riscv-tests p env incl. rv64mi/si/ua/uc, OpenSBI + Linux + '
           'busybox boot to the shell with a checkpoint round trip, and the commit-log comparison with Spike; '
           'needs sim/cpu/sys/build_all.sh outputs in build/third-party/linux-lab/out and build_spike.sh',
}
# Presets expand to suites. release-patch is build/cpu/ooo-debug/coord/vcheck.sh;
# release-minor adds the full Icarus run (full_check.sh).
PRESETS = {
    'release-patch': ['isa', 'bench-smoke', 'spike-lockstep'],
    'release-minor': ['isa', 'bench-smoke', 'icarus-full', 'spike-lockstep'],
}
DEFAULT_CACHE_SIZES = ('default', '2')   # tb_core's 512 beats (4 KiB) and 2-beat (1-line) L1s
# Icarus runs of test_cpu that do not fit in 300 s, split into shards (test_cpu balances them by golden-model length).
# Measured 2026-11-22 (Icarus 12): ooo with default caches, one quarter 102 s on a quiet
# machine but 190-211 s with other runs going; with 2-beat caches one eighth 68 s quiet.
# Sized for about 2x headroom under load.
ICARUS_SHARDS = {('ooo', 'default'): 6, ('ooo', 'small'): 12}
OOO_ONLY = ('fpu', 'vector', 'dline', 'n_miss', 'ld_lat', 'l0', 'l0_lat')


@dataclass(frozen=True)
class Bench:
    """A build_bench.py output folder (built once, reused while its input hashes match)."""
    name: str                       # folder under --bench-root; vcheck.sh's names where they exist
    args: tuple                     # build_bench.py arguments, without --out-dir and tool paths
    benchmark: str = 'dhrystone'


DHRY_REF = Bench('vl-dhrystone-rv64imb-ooo', ('--benchmark', 'dhrystone', '--ram-kib', '64', '--isa',
                 'rv64im_zba_zbb_zbs_zifencei', '--runtime', 'reference'))
DHRY_FAST = Bench('vl-dhrystone-rv64imb-fastrt-ooo', ('--benchmark', 'dhrystone', '--ram-kib', '64', '--isa',
                  'rv64im_zba_zbb_zbs_zifencei', '--runtime', 'fast'))
LZMA_D12 = Bench('lzma-d12-rv64imb-ooo', ('--benchmark', 'lzma', '--lzma-dict-log', '12'), 'lzma')
FD_ISA = 'rv64imfd_zba_zbb_zbs_zifencei'


@dataclass
class Step:
    name: str
    suites: tuple
    script: str                     # repository-relative Python script
    args: list                      # its arguments; Path-like values are tagged by suite.py
    parser: str                     # key of suite.py PARSERS
    tags: tuple = ()
    core: str | None = None         # the core this step simulates (None: no core)
    candidate: bool = False         # --core-source applies to this step
    sim: str | None = None          # fixed simulator; None: the --sim option
    side: str = 'linux'             # linux (WSL from Windows) | llvm (where Windows LLVM is) | host
    runner: str | None = None       # 'test_cpu' or 'run_bench': which knobs pass through
    bench: Bench | None = None
    out_arg: str | None = '--out-dir'   # how the step gets its private output folder (None: none)
    needs: list = field(default_factory=list)
    lock: str | None = None         # steps with the same lock never run at once (shared bench folder)
    weight: int = 1                 # simulations the step runs at once (counts against --jobs)
    est: int = 60                   # rough seconds, for --list
    when: str | None = None         # 'core-has-fpu' | 'runner-has:<script>:<flag>' | 'bench-exists:<name>'
    expect_fail: str | None = None  # negative control: regex the failure output must match
    mutate: tuple | None = None     # (old, new): the negative control's one-line mutation of the core
    shard: tuple | None = None      # (K, N) for test_cpu --shard; set by suite.py when it splits
    note: str = ''


def cache_args(size):
    return [] if size == 'default' else ['--icache-beats', size, '--dcache-beats', size]


def cache_tag(size):
    return '' if size == 'default' else f'-{size}beat'


def is_small(size):
    return size != 'default' and int(size) < 512


def test_cpu_step(name, suites, core, size, sim, extra=(), tags=(), when=None, candidate=True, est=120):
    return Step(name, suites, 'sim/cpu/test_cpu.py', ['--core', core, '--sim', sim, *cache_args(size), *extra],
                'test_cpu', tags=('test_cpu', sim, core, *tags), core=core, candidate=candidate and core == 'ooo',
                sim=sim, runner='test_cpu', when=when, est=est)


def unit(ctx):
    yield Step('unit-fp-golden', ('unit',), 'sim/cpu/fp_cases.py', [], r'count:^PASS: (\d+) FP cases',
               tags=('python',), out_arg=None, est=10)
    yield Step('unit-program-inputs', ('unit',), 'sim/cpu/test_program_inputs.py', [], 'unittest',
               tags=('python',), out_arg=None, est=5)
    yield Step('unit-suite-selftest', ('unit',), 'sim/cpu/suite.py', ['--self-test'],
               r'count:^PASS: suite self-test, (\d+) checks', tags=('python',), out_arg=None, est=5)


def isa(ctx):
    for core in ctx.cores:
        for size in ctx.cache_sizes:
            yield test_cpu_step(f'isa-{core}{cache_tag(size)}', ('isa',), core, size, ctx.sim,
                                est=150 if ctx.sim == 'verilator' else 400)


def fpu(ctx):
    for size in ctx.cache_sizes:
        yield test_cpu_step(f'fpu-ooo{cache_tag(size)}', ('fpu',), 'ooo', size, ctx.sim, ['--fpu'],
                            tags=('fpu',), when='core-has-fpu', est=180)


def vector(ctx):
    for size in ctx.cache_sizes:
        yield test_cpu_step(f'vector-ooo{cache_tag(size)}', ('vector',), 'ooo', size, ctx.sim, ['--vector'],
                            tags=('vector',), when='runner-has:sim/cpu/test_cpu.py:--vector', est=180)


def bitmanip(ctx):
    for core in ctx.cores:
        yield Step(f'bitmanip-{core}', ('bitmanip',), 'sim/cpu/check_bitmanip.py', ['--core', core],
                   r'count:^PASS: identical results for all (\d+) groups', tags=('icarus', core), core=core,
                   sim='icarus', out_arg=None, lock='bitmanip', est=120,
                   note='tests the rtl/cpu file (check_bitmanip.py has no --core-source)')


def run_bench_step(name, suites, bench, extra=(), tags=(), parser=None, when=None, est=150, weight=1, **kw):
    kind = bench.benchmark
    return Step(name, suites, 'sim/cpu/bench/run_bench.py',
                ['--benchmark', kind, '--core', 'ooo', '--sim', None, *extra], parser or kind,
                tags=('run_bench', kind, *tags), core='ooo', candidate=True, runner='run_bench', bench=bench,
                out_arg='--out-dir:bench', lock=bench.name, when=when, est=est, weight=weight, **kw)


def bench_smoke(ctx):
    both = ('bench-smoke', 'bench')
    yield run_bench_step('lzma-64k', both, LZMA_D12, est=150)
    yield run_bench_step('lzma-4k', ('bench-smoke',), LZMA_D12,
                         ['--icache-beats', '512', '--dcache-beats', '512', '--no-differential'], est=150)
    yield run_bench_step('dhry-ref', both, DHRY_REF, est=60)
    yield run_bench_step('dhry-fast', ('bench-smoke',), DHRY_FAST, est=60)
    # Regression watch (user, 2026-11-22): the same with the FP option built in, when the core has it.
    for name, bench, extra in (('lzma-64k-fpu', LZMA_D12, []), ('dhry-ref-fpu', DHRY_REF, []),
                               ('dhry-fast-fpu', DHRY_FAST, [])):
        yield run_bench_step(name, ('bench-smoke',), bench, [*extra, '--fpu'], tags=('fpu',),
                             when='core-has-fpu', est=150)


# Further benchmarks of the bench suite. Each: (name, Bench for integer, Bench for --fpu, run args, split).
# split: run_bench --pieces ranges, each one invocation under 300 s, then --pieces merge.
BENCH_RUNS = [
    ('rt', Bench('rt-g16s2i32-pt16x12x4-rv64imb', ('--benchmark', 'rt'), 'rt'),
     Bench('rt-g16s2i32-pt16x12x4-rv64imfdb', ('--benchmark', 'rt', '--isa', FD_ISA), 'rt'),
     ['--rt-mode', 'sampled', '--jobs', '2'], None, 2),
    # 9 kernels, one piece each, one invocation per piece, then merge. Three pieces per invocation
    # (the coordinator's 02:41 run, --jobs 3) timed out here at load 15 with --jobs 2.
    ('js', Bench('js-s1-rv64imb', ('--benchmark', 'js'), 'js'),
     Bench('js-s1-rv64imfdb', ('--benchmark', 'js', '--isa', FD_ISA), 'js'),
     ['--sample-pieces', '1', '--jobs', '1'], [(i, i + 1) for i in range(9)], 1),
    ('mm', Bench('mm-small-rv64imb', ('--benchmark', 'mm'), 'mm'),
     Bench('mm-small-rv64imfdb', ('--benchmark', 'mm', '--isa', FD_ISA), 'mm'), [], None, 1),
    ('ternary', Bench('ternary-small-i2+lut5w+bs8-rv64imb', ('--benchmark', 'ternary'), 'ternary'),
     Bench('ternary-small-i2+lut5w+bs8-rv64imfdb', ('--benchmark', 'ternary', '--isa', FD_ISA), 'ternary'), [], None, 1),
]


def bench(ctx):
    for kind, plain, fd, extra, split, weight in BENCH_RUNS:
        b = fd if ctx.fpu else plain
        when = f'bench-exists:{kind}'
        parser = kind if kind in ('rt', 'js') else 'bench'
        if not split:
            yield run_bench_step(f'bench-{kind}', ('bench',), b, extra, parser=parser, when=when, est=280,
                                 weight=weight)
            continue
        parts = []
        for a, z in split:
            parts.append(f'bench-{kind}-p{a}-{z}')
            yield run_bench_step(parts[-1], ('bench',), b, [*extra, '--pieces', f'{a}:{z}'], parser='pieces',
                                 when=when, est=200, weight=weight, tags=('piece',))
        yield run_bench_step(f'bench-{kind}', ('bench',), b, [*extra, '--pieces', 'merge'], parser=parser,
                             when=when, est=30, needs=parts)


def icarus_full(ctx):
    s = ('icarus-full',)
    yield test_cpu_step('full-ooo', s, 'ooo', 'default', 'icarus', est=420)
    yield test_cpu_step('full-ooo-2line', s, 'ooo', '2', 'icarus', est=1200)
    yield Step('full-bitmanip', s, 'sim/cpu/check_bitmanip.py', ['--core', 'ooo'],
               r'count:^PASS: identical results for all (\d+) groups', tags=('icarus', 'ooo', 'bitmanip'),
               core='ooo', sim='icarus', out_arg=None, lock='bitmanip', est=120,
               note='tests the rtl/cpu file (check_bitmanip.py has no --core-source)')
    yield test_cpu_step('full-multicycle', s, 'multicycle', 'default', 'icarus', est=200)
    yield test_cpu_step('full-pipe', s, 'pipe', 'default', 'icarus', est=200)


def soc(ctx):
    yield Step('soc-memory', ('soc',), 'sim/cpu/check_soc_memory.py', [], 'soc_memory', tags=('icarus',),
               sim='icarus', est=60)
    yield Step('soc-btb-reach', ('soc',), 'sim/cpu/check_btb_reach.py', ['@core', '@out', '--sim', None],
               'btb', tags=('ooo',), core='ooo', candidate=True, out_arg=None, est=60)


def negative(ctx):
    # The XOR register-register result becomes OR: any program using xor must diverge.
    yield Step('negative-xor-or', ('negative',), 'sim/cpu/test_cpu.py', ['--core', 'ooo', '--sim', None],
               'test_cpu', tags=('negative', 'ooo'), core='ooo', candidate=True, runner=None,
               expect_fail=r'AssertionError: \S+ stall=\d+ event \d+', mutate=('4: r = x ^ y;', '4: r = x | y;'),
               est=150, note='passes only if test_cpu FAILS on the mutant with a trace mismatch')


RVT = 'sim/cpu/riscv_tests/run_riscv_tests.py'
RVT_INT = ('rv64ui', 'rv64um', 'rv64uzba', 'rv64uzbb', 'rv64uzbs')
RVT_FP = ('rv64uf', 'rv64ud')
RVT_TREE = 'path-exists:build/third-party/riscv-tests-src/riscv-tests/isa'
RVT_NOTE = ('riscv-tests 3df703c fetched by sim/cpu/fetch_riscv_tests.sh (SHA-256 lock); '
            'rv64ui/ma_data is an expected cause-4 trap (misaligned data traps by contract), not a pass')
# Measured 2026-11-22 (WSL, load average about 18): golden models 58-84 s for the integer set; Icarus
# multicycle with 2-beat caches at stalls 0 and 7 70 s, pipe rv64ui 38 s; Verilator ooo 2-beat 60 s with a
# cached build (a fresh Verilator build adds about 2 minutes); F/D 16 s cached.


def rvt_step(name, args, est, core=None, sim=None, when=RVT_TREE, tags=(), candidate=False,
             parser=r'count:^PASS: (\d+) riscv-tests'):
    return Step(name, ('riscv-tests',), RVT, list(args), parser, tags=('riscv-tests', *tags, *filter(None, (sim, core))),
                core=core, candidate=candidate, sim=sim, est=est, when=when, note=RVT_NOTE)


def riscv_tests(ctx):
    # Harness negative controls: a mutated add.S must fail as test 3 on every model, an unexpected trap
    # or an expected trap that passes must fail, and trace differences must be found.
    yield rvt_step('rvt-selftest', ['--self-test', '--core', 'pipe', '--sim', 'icarus', '--stalls', '0,7'], 30,
                   core='pipe', sim='icarus', tags=('negative',),
                   parser=r'count:^PASS: riscv-tests self-test, (\d+) checks')
    yield rvt_step('rvt-golden', RVT_INT, 90, tags=('python',))
    yield rvt_step('rvt-golden-fp', RVT_FP, 40, tags=('python', 'fpu'))
    for size in ctx.cache_sizes:
        tag = cache_tag(size)
        yield rvt_step(f'rvt-ooo{tag}', ['--core', 'ooo', '--sim', 'verilator', '--stalls', '0,7', *cache_args(size),
                                         *RVT_INT], 200, core='ooo', sim='verilator', candidate=True)
        yield rvt_step(f'rvt-ooo-fpu{tag}', ['--core', 'ooo', '--sim', 'verilator', '--stalls', '0,7',
                                             *cache_args(size), *RVT_FP], 180, core='ooo', sim='verilator',
                       candidate=True, when=f'{RVT_TREE} & core-has-fpu', tags=('fpu',))
        for core in ('pipe', 'multicycle'):
            yield rvt_step(f'rvt-{core}{tag}', ['--core', core, '--sim', 'icarus', '--stalls', '0,7',
                                                *cache_args(size), *RVT_INT], 150, core=core, sim='icarus')


SL = 'sim/cpu/spike_lockstep.py'
SL_INT = ('rv64ui', 'rv64um', 'rv64uzba', 'rv64uzbb', 'rv64uzbs')
SL_NOTE = 'RTL trace vs Spike record by record (pc, insn, register write, store address/data/width, final trap)'


def spike_lockstep(ctx):
    s = ('spike-lockstep',)
    pat = r'count:^PASS: (\d+) records of \d+ runs'
    # Measured 2026-11-22 (WSL, Verilator, load about 15): riscv-tests 80-115 s per core and cache size, F/D 30 s;
    # Dhrystone 4-12 s per run; LZMA d12 whole (4.18M instructions) 15-40 s; rt/js pieces 3 x 200k 15-30 s.
    for core in ('ooo', 'pipe', 'multicycle'):
        cand = core == 'ooo'
        tags = ('spike', core, 'verilator')
        kw = dict(core=core, candidate=cand, sim='verilator', note=SL_NOTE)
        for size in ctx.cache_sizes:
            tag = cache_tag(size)
            yield Step(f'spike-rvt-{core}{tag}', s, SL, ['rvt', *SL_INT, '--core', core, '--sim', 'verilator',
                                                         *cache_args(size)], pat, tags=tags, out_arg=None, est=150, **kw)
            # LZMA d12: whole with the default caches at wait pattern 0; with small caches (232 s whole on the
            # out-of-order core, too close to the limit) its first 1.5M instructions at wait pattern 7
            small = [] if size == 'default' else ['--max', '1500000']
            yield Step(f'spike-lzma-{core}{tag}', s, SL, ['image', '--core', core, '--sim', 'verilator',
                                                          '--stalls', '0' if size == 'default' else '7', *small,
                                                          *cache_args(size)],
                       pat, tags=tags, bench=LZMA_D12, out_arg='--out-dir:bench', lock=LZMA_D12.name, est=60, **kw)
        yield Step(f'spike-dhry-{core}', s, SL, ['image', '--core', core, '--sim', 'verilator', '--stalls', '0,7'],
                   pat, tags=tags, bench=DHRY_REF, out_arg='--out-dir:bench', lock=DHRY_REF.name, est=30, **kw)
    yield Step('spike-rvt-ooo-fpu', s, SL, ['rvt', 'rv64uf', 'rv64ud', '--fpu', '--core', 'ooo', '--sim', 'verilator'],
               pat, tags=('spike', 'ooo', 'fpu'), core='ooo', candidate=True,
               sim='verilator', out_arg=None, when='core-has-fpu', est=90, note=SL_NOTE)
    for kind, _plain, fd, *_ in BENCH_RUNS:
        if kind not in ('rt', 'js'):
            continue
        yield Step(f'spike-{kind}-pieces-ooo-fpu', s, SL, ['pieces', '--fpu', '--core', 'ooo', '--sim', 'verilator',
                                                           '--pieces', '3', '--window', '200000'],
                   pat, tags=('spike', 'ooo', 'fpu', 'piece'), core='ooo',
                   candidate=True, sim='verilator', bench=fd, out_arg='--out-dir:bench', lock=fd.name,
                   when=f'core-has-fpu & bench-exists:{kind}', est=90,
                   note='3 rv_iss checkpoint windows of 200k instructions, restored by the stub on the core')
    yield Step('spike-selftest', s, SL, ['self-test'], r'count:^PASS: spike-lockstep self-test, (\d+) checks',
               tags=('spike', 'python', 'negative'), out_arg=None, est=5)
    # Negative control: the suite's XOR->OR mutant of the core must be caught by a register-value difference in
    # rv64ui/xor (an infrastructure failure does not count).
    yield Step('spike-negative-xor-or', s, SL, ['rvt', 'rv64ui', '--core', 'ooo', '--sim', 'verilator'], 'unittest',
               tags=('spike', 'negative', 'ooo'), core='ooo', candidate=True, sim='verilator', out_arg=None,
               expect_fail=r'^FAIL rv64ui-xor \(stall \d+\): differs at record \d+: spike \S+ \(0x[0-9a-f]{8}\) x\d+=\S+; rtl \S+ \(0x[0-9a-f]{8}\) x\d+=',
               mutate=('4: r = x ^ y;', '4: r = x | y;'), est=60,
               note='passes only if the lockstep FAILS on the mutant core, at an XOR')


def sys_mode(ctx):
    yield Step('sys-riscv-tests', ('sys',), 'sim/cpu/sys/riscv_tests.py', [],
               r'count:^PASS: (\d+) riscv-tests pass', tags=('python', 'sys'), out_arg=None, est=60, lock='sys-tests',
               note='rv64ui/um/ua/uf/ud/uc/mi/si p env; ma_data and pmpaddr are expected failures')
    yield Step('sys-boot', ('sys',), 'sim/cpu/sys/sys_boot.py', [], r'count:^PASS: (\d+) sys-boot instructions',
               tags=('python', 'sys'), est=30, note='Linux to the busybox shell, poweroff, RVISSST3 round trip')
    # With Spike built (sim/cpu/sys/build_spike.sh): the riscv-tests and the whole boot in lockstep.
    yield Step('sys-riscv-tests-spike', ('sys',), 'sim/cpu/sys/riscv_tests.py', ['--spike', 'auto'],
               r'count:^PASS: (\d+) riscv-tests pass', tags=('python', 'sys', 'spike'), out_arg=None, est=120,
               lock='sys-tests',
               note='commit logs against Spike; rv64mi-ma_fetch is a known difference (misa.C writable in Spike)')
    yield Step('sys-spike-boot', ('sys',), 'sim/cpu/sys/spike_compare.py', ['--instructions', '100000000', '--min',
               '40000000', '--expect-finisher-end'], r'count:^PASS: (\d+) instructions of the boot equal',
               tags=('python', 'sys', 'spike'), out_arg=None, est=60,
               note='OpenSBI + Linux + busybox boot to power-off, rv_iss --time spike vs Spike')


def repo(ctx):
    yield Step('repo-check', ('repo',), 'scripts/check_repo.py', [], 'check_repo', tags=('python',),
               side='host', out_arg=None, est=60)
    yield Step('repo-site', ('repo',), 'scripts/build_site.py', [], r'count:^site: (\d+) artworks',
               tags=('python', 'writes-docs'), side='host', out_arg=None, est=30,
               note='rewrites docs/; review git diff docs afterwards')


GENERATORS = {'unit': unit, 'isa': isa, 'fpu': fpu, 'vector': vector, 'bitmanip': bitmanip,
              'bench-smoke': bench_smoke, 'bench': bench, 'icarus-full': icarus_full, 'soc': soc,
              'riscv-tests': riscv_tests, 'negative': negative, 'repo': repo, 'sys': sys_mode,
              'spike-lockstep': spike_lockstep}
