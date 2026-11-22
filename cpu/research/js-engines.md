# JavaScript engines on our RV64 core: weaknesses, a benchmark to optimise against, and a plan

Research report, 2026-11-22 01:09-01:40 EST (times from `date` in WSL). Research agent for the council.
Read-only for the repository: everything new is in the ignored `build/research/` (this file and
`build/research/js/`). Nothing in `rtl/`, `sim/`, `cpu/` or `DEVLOG.md` was edited and nothing was
committed. Repository HEAD was `e8eeae3` at the start and `c607485` at the end (another session
committed meanwhile); the prototype used the working-tree `sim/cpu/bench/rv_iss.c` (git blob
`17e0a038`, unmodified) and `sim/cpu/bench/start.S` read-only.

Labels: **Fact** (read in a file at the line given, in official source at a pinned commit, or
measured here), **Judgement** (my inference). Web facts came through two research sub-agents that
read the official sources; their file readings were partial in places, which is noted.

---

## 0. Summary

- **No production JS engine can run on our core today.** V8 (and so Node) and JavaScriptCore (and so
  Bun) need rv64gc *plus Linux*: A (LR/SC and AMOs), F/D, Zicsr, an icache-flush syscall, mmap and
  mprotect, threads and signals. Bun has no riscv64 target at all. A bare-metal engine is the only
  option now.
- **A bare-metal JavaScript benchmark now runs.** QuickJS-ng v0.18.0 (MIT) builds unmodified for
  rv64imfd_zba_zbb_zbs and for rv64imb (soft float) against a 51-symbol shim libc of my own. It runs
  9 deterministic kernels on rv_iss. Each kernel prints one checksum line.
  - The output hash `06484b07bf7fe92f` is identical on both RISC-V builds and on a native aarch64
    build of the same engine and script on the laptop.
  - Hard-float run: 281.3M instructions in all, 24-47M per kernel, plus 6.2M for engine start-up
    and parse.
- **Top weaknesses, measured on the interpreter's own traces:**
  1. **The instruction cache's organisation.** It is direct-mapped with 8-byte lines, blocking,
     lowest bus priority and has no prefetch. At 64 KiB it misses 1.2-58.6 times per thousand
     instructions (MPKI); a 4-way cache of the same size with 64 B lines misses 0-3.5 MPKI. The
     interpreter loop `JS_CallInternal` alone is 57.8 KB.
  2. **No indirect-target predictor with history.** There are 18-41 indirect jumps per thousand
     instructions. The BTB's last-target prediction misses 4-55% of them (0.8-17.4 MPKI); an
     idealised path-history predictor gets 0.2-6.9 MPKI.
  3. **BTB capacity and organisation:** 7-19 BTB misses per thousand instructions on 63-95 taken
     transfers per thousand.
  4. **Guards that test a just-loaded value.** In 11-40% of conditional branches, a load at most 4
     instructions earlier produced an operand.
  5. **ISA:** A, C, Zicond and misaligned access are missing. FENCE.I clears the whole I-cache.
  6. **No OS and no MMU**, which blocks every JIT engine.
- **Proposed goal (not set):** the laptop + 50% per clock, kernel by kernel. On the preliminary
  laptop probe this needs about 7.4-10 RISC-V instructions per clock (IPC), because the X925 already
  runs this interpreter at an IPC of 4.0-5.6 with 1.19-1.29x fewer instructions.

---

## 1. Our chip: verified facts

| Item | Fact (file:line) |
|---|---|
| ISA | rv64im + Zba/Zbb/Zbs + Zifencei. No A, C or V, no privilege traps, interrupts or MMU (`cpu/architecture.md:11`). F/D is the 0.17.0 option `RV64_OOO_FPU`, default off, with Zicsr for fcsr only (`architecture.md:37-64`). RVV is in progress (BOARD 00:24, `build/cpu/fp/RVV-CONTRACT.md`). |
| CSRs | Only fflags, frm and fcsr, with the FPU option; any other CSR is cause 2 (`architecture.md:41,153`). No Zicntr (`:154`); benchmarks time with mailbox markers. |
| Alignment | Misaligned loads and stores trap (`architecture.md:30`, ledger `:162`). |
| FENCE.I | Satisfied by completing stores and refetching (`architecture.md:140`). The out-of-order core clears **every** I-cache valid bit at a retiring FENCE.I (`rtl/cpu/rv64_ooo.sv:1912`). A retiring store already clears the matching I-cache beat (`:1896`), and a store to an already-fetched younger instruction flushes it (`:1897`, smc). |
| EEI | Bare metal: start.S sets the stack, clears .bss, calls main, writes the mailbox and runs EBREAK (`sim/cpu/bench/start.S`). rv_iss stops at ECALL, EBREAK or any fault (`rv_iss.c:6`). No syscalls, no mmap. |
| Width | Fetch and rename are 32 wide (`rv64_ooo.sv:126`, FW). Retirement is 32 wide (RW). ROB 512, IQ 128 (`:127,138`). 8 ALUs, 4 of them branch units, 4 loads and 3 store addresses (`:142-145`). |
| BTB | 1024 entries, direct-mapped by PC[11:2], 10-bit partial tag, 2-bit counter, **one target per PC** stored as a signed offset (`:165-167, 609-623`). Trained at retirement on taken transfers (`:1878-1888`). A non-return JALR is predicted from this entry alone (`:2455-2460`). **There is no history-indexed indirect predictor.** |
| Direct prediction | 6-table TAGE-like predictor with 128 bits of history (`:649-657`), a 1024-entry loop predictor (`:170-172`), and predecode of JAL, return and backward branches (`:2497-2506`). Up to 4 taken transfers and 4 conditional branches per fetch group (`:173, 653`). |
| RAS | 64 entries, group-local copy, up to 4 calls or returns per group (`:168, 177`). Displaced returns are predicted (`architecture.md:88`, 0.14.11). |
| I-cache | Direct-mapped (one tag per index, `:2444-2446`), **8-byte lines**: a miss fills one beat per bus read (`:1638-1642`). The default is 128 KiB (`:11`); measured runs use 4 KiB (SoC, Dhrystone) or 64 KiB (7-Zip, `cpu/7zip-benchmark-targets.md:164`). An instruction fetch is a blocking read with the **lowest bus priority** (`architecture.md:88`, "store write, entry 0, younger entries, then instruction fetch"). No prefetch. |
| D-cache | Two-way, 8-byte lines, write-through (`architecture.md:28, 88`). Up to 8 misses in flight since 0.16.0 (`N_MISS`). |
| Front-end depth | `FE_DEPTH` defaults to 0, the idealised refill (`:633`). At 8, a mispredict refills in about 10 clocks (`architecture.md:88`, 0.14.5). |
| Other speculation | Value prediction on loads, multiplies and divides: 256 entries, 32 equal results before predicting (`:819-823`, 0.15.1). ALU-pair fusion, also across rename groups (0.11.2, 0.16.1). Rename folding of `addi`, `lui`, `jal` and constant `jalr` (0.12.3). A 4096-entry load-wait table (`:944`). |

---

## 2. Engine review (official sources, pinned)

### 2.1 Sources

| Engine | Pinned | URL |
|---|---|---|
| V8 | commit `acf7e405a8d24e741a338736e890ef0ae0abdfc8` (main, 2026-11-22, `v8-version.h` 16.0.0.0) | https://github.com/v8/v8/tree/acf7e405a8d24e741a338736e890ef0ae0abdfc8 |
| Chromium `config/riscv.gni` | refs/heads/main (blob 2362042291a4) | https://chromium.googlesource.com/chromium/src/build/+/refs/heads/main/config/riscv.gni |
| Node.js | commit `2b365b28928d9ab36f1e9b41f81beaca83fa772a` (main, 2026-11-21; bundles V8 15.8.62.44) | https://github.com/nodejs/node/blob/2b365b28928d9ab36f1e9b41f81beaca83fa772a/BUILDING.md |
| WebKit / JavaScriptCore | commit `e7c46702d1c2040f947185d1612a67a740f8c091` (2026-11-22) | https://github.com/WebKit/WebKit/tree/e7c46702d1c2040f947185d1612a67a740f8c091/Source/JavaScriptCore |
| Bun | not pinned: the live install script plus GitHub PRs | https://bun.sh/install , https://github.com/oven-sh/bun/pull/21924 , /pull/27522 , /pull/41385 |
| QuickJS-ng (prototype) | tag v0.18.0, commit `d7215b0ad3fc2c562e8317fd9bca058fd4863804` | https://github.com/quickjs-ng/quickjs/archive/refs/tags/v0.18.0.tar.gz (SHA-256 `28bcd89aa3683fd2a946537e5ce3f11cc46b5cbf3383c7561aaef3df5ff9f1dd`, 910,210 bytes) |

Licences: V8 is BSD-3, Node and Bun are MIT, JavaScriptCore is BSD/LGPL and QuickJS-ng is MIT. Nothing
was copied into the repository; this report summarises.

### 2.2 Ports and tiers on riscv64

- **V8 (Fact):**
  - riscv64 has every tier: Ignition, Sparkplug (`src/baseline/riscv`), Maglev (`src/maglev/riscv`),
    TurboFan/Turboshaft (`src/compiler/backend/riscv`) and Liftoff for Wasm. The assembler is in
    `src/codegen/riscv`, with one extension file each for a, b, c, d, f, m, v, zfa, zfh, zicond, zicsr,
    zifencei and zimop.
  - RISE (2025-12-09) describes the port as "mostly at feature parity" and running the full JetStream
    suite: https://riseproject.dev/2025/12/09/a-glimpse-into-v8-development-for-risc-v/
  - The build profile defaults to rv64gc. RVV, Zba/Zbb/Zbs, Zicond and Zicfiss are off by default
    (`riscv.gni`).
  - Run-time detection uses `riscv_hwprobe`, falling back to `/proc/cpuinfo`. It finds F/D, V, B, Zfa,
    Zfh and C, but never Zicond.
  - JIT code uses C only in an RVA23-profile build.
- **Node (Fact):** riscv64 Linux is **Experimental** (kernel 5.19 or later, glibc 2.36 or later): there
  are no official releases. Unofficial builds exist; v26.13.1 ships only
  `linux-riscv64-pointer-compression` (https://unofficial-builds.nodejs.org/download/release/index.json).
- **JavaScriptCore (Fact):**
  - LLInt (offlineasm `riscv64.rb`), Baseline JIT, DFG and the YARR regex JIT are enabled through
    CMake (`Source/cmake/WebKitFeatures.cmake`, the `WTF_CPU_RISCV64` branch). FTL is forced off
    (`runtime/Options.cpp`, bug 239707). There is no RISCV64 Air backend (`b3/air/AirOpcode.opcodes`).
    WebAssembly is interpreter-only.
  - The assembler encodes I, M, A, F and D only: **no C, Zba, Zbb or Zicond**. CLZ is a loop and popcount
    is "unsupported".
  - CAS uses LR/SC.
  - JIT memory is one RWX pool, 32 MB on RISCV64, obtained by mmap.
  - It flushes with `__builtin___clear_cache` on every repatch.
- **Bun (Fact):** the installer exits with "Not supported on riscv64". A port PR (#27522) was closed and
  PR #41385 removed the riscv code paths. Judgement: a port would get JSC's LLInt, Baseline and DFG.

### 2.3 ISA dependencies

| Feature | V8 / Node | JSC / Bun | QuickJS-ng (prototype) | Our core |
|---|---|---|---|---|
| A (LR/SC, AMO) | **Required**: TurboFan atomics are LR/SC loops; concurrent marking uses atomic mark bits and CAS (https://v8.dev/blog/concurrent-marking); C++ runtime and libatomic (Fact) | **Required**: CAS on LR/SC (Fact) | Not needed: built with atomics and threads off (`-D__DJGPP`, quickjs.c:75, cutils.h:641) | Missing |
| F/D | Required: V8's FPU feature needs `__riscv_f` and `__riscv_d` (Fact) | Required (Fact) | Optional: soft float works (+8% instructions overall, +44% on navier, measured) | 0.17.0 option |
| C | JIT code uses no C in a default build, but distro binaries are rv64gc and contain it (Fact / Judgement) | Never emitted (Fact) | Not used (`-march` without c) | Missing |
| Zba/Zbb/Zbs | Optional: `zext.w` cuts pointer decompression from 5 instructions to 2, and `sh*add` halves address arithmetic (RISE post, Fact) | Not used (Fact) | Used by clang | Implemented |
| Zicond | Optional, off by default, not probed (Fact) | Not used | Not used | Missing |
| Misaligned access | Not required: byte-wise helpers (partial reading, Judgement) | Not established | Not needed | Traps |
| Instruction-cache flush | `__NR_riscv_flush_icache` syscall, all harts, on code finalisation and patching (`cpu-riscv.cc`, Fact) | `__builtin___clear_cache` on every inline-cache or jump repatch (Fact) | Not needed (no JIT) | FENCE.I clears the whole I-cache |
| Pointer tagging | Pointer compression: 31-bit Smis, 4 GB cage, `lwu` plus a base add (https://v8.dev/blog/pointer-compression). On riscv64 it is not a default but the shipped unofficial Node build uses it | NaN-boxing: NumberTag `0xfffe000000000000` pinned in x25, NotCellMask in x26; doubles stored +2^49; a check is an AND, a compare and a branch (`JSCJSValue.h`, Fact) | 16-byte JSValue {value, tag}; the tag check is a load, compare and branch | Has `add.uw`, `sext.w`, `sh*add`, `andn` and `orc.b` |
| Counters (Zicntr) | OS clock, no `rdcycle` seen (partial reading) | OS clock | `gettimeofday`, fixed in the shim | Missing |
| V | Wasm SIMD on RVV-256/512 (RISE post) | No | No | In progress |
| Privilege / OS | mmap/mprotect (W^X), pthreads, signals (the Wasm trap handler), hwprobe, Sv39/48 MMU (Sv57 with pointer compression is fatal) (Fact) | mmap of RWX pages, threads, Linux (Fact) | None | None |

### 2.4 Hot spots documented by the engines and in published studies

- **Interpreter dispatch.**
  - Ignition handlers end in a threaded indirect tail-jump through the dispatch table (V8
    `interpreter-assembler.cc`, Fact). LLInt dispatches the same way.
  - QuickJS-ng with `DIRECT_DISPATCH` uses computed goto (quickjs.c:52-54), so it has many indirect
    jump sites: 44-129 static sites per kernel, measured.
  - Studies:
    - Rohou, Swamy and Seznec, CGO 2015 (https://researchr.org/publication/RohouSS15): dispatch MPKI
      fell from 12.8 on Nehalem to 1.4 on Haswell, and simulated ITTAGE nearly removes it. The figures
      are second-hand, from https://www.python.org/pipermail/python-dev/2015-August/141172.html; the
      PDF was not readable.
    - Seznec's ITTAGE (https://www.jilp.org/jwac-2/program/JWAC-2-program.htm) is the reference
      history-based indirect predictor.
- **Instruction cache and iTLB.**
  - Node.js/V8 runs at 61.2 L1I MPKI with a 32 KB cache, against 14.4 for SPEC, and iTLB at 2.29 MPKI
    against 0.03 (Zhu et al., MICRO 2015, https://edge.seas.harvard.edu/resource/paper-19).
  - AsmDB (ISCA 2019,
    https://research.google/pubs/asmdb-understanding-and-mitigating-front-end-stalls-in-warehouse-scale-computers/)
    reports front-end stalls in datacenter (not JS) code.
- **Type and shape checks.**
  - 12.9% of dynamic instructions (Checked Load, HPCA 2011, https://bibtex.github.io/HPCA-2011-AndersonFCE.html).
  - 6.2% in V8, with +2.2% gain from removing them on a large core (IISWC 2016,
    https://unpaywall.org/10.1109%2FIISWC.2016.7581268).
  - About 8% on JetStream2 (IISWC 2021,
    https://computer.org/csdl/proceedings-article/iiswc/2021/417300a013/1A8gkoPvuyk).
  - Typed Architectures on a RISC-V Rocket: +11.2% on SpiderMonkey for +1.6% area (ASPLOS 2017).
- **Write barriers.** In Java a generational barrier costs under 2% on average and 6% at worst
  (Blackburn and Hosking, ISMM 2004). I found no study of hardware barriers for JS.
- **ISA precedent.** Arm FJCVTZS (JS double-to-int32): +0.5-1% on JetStream2 in WebKit
  (https://trac.webkit.org/r237136).
- **RISC-V J extension.** It delivered pointer masking (Supm/Smnpm) and nothing JIT-specific
  (https://github.com/riscv/riscv-j-extension).
- **Not found:** a published per-clock Speedometer or JetStream comparison across CPUs.
- **The JIT cost model (Judgement from the sources):**
  - Sparkplug removes operand decoding and dispatch (+5-10% on Speedometer, https://v8.dev/blog/sparkplug).
  - Jitless V8 is about 40% slower on Speedometer 2 (https://v8.dev/blog/jitless).
  - "Short builtin calls" exists because far indirect calls to embedded builtins mispredict
    (https://v8.dev/blog/short-builtin-calls).
  - JSC flushes on every repatch, so warm-up issues many small code writes and flushes.

---

## 3. Where our core is weak for JS

### 3.1 Measured: trace statistics of the QuickJS-ng kernels (Fact; model, not RTL)

rv_iss traces of a 1.5M-instruction window per kernel, starting 30% into the kernel. The first 0.3M
instructions warm the models and 1.2M are counted (`build/research/js/analyze.py`). Hard-float image.
Cache, BTB and indirect-predictor figures come from simple trace models, not from our RTL.

| Kernel | Indirect jumps per KI | Last-target miss | Last-target MPKI | Path-history MPKI (ideal) | BTB 1k DM misses per KI | Taken per KI | I$ DM 8 B 4 KiB MPKI | I$ DM 8 B 64 KiB | I$ 4-way 64 B 32 KiB | I$ 4-way 64 B 64 KiB | Code touched (KiB, 64 B lines) | Cond. branches within 4 of a load | Loads / stores % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| props | 20.4 | 39.7% | 8.07 | 2.37 | 11.7 | 62.7 | 286 | 37.7 | 5.1 | 0.22 | 14.2 | 34.5% | 28.3 / 15.0 |
| sched | 25.3 | 55.1% | 13.93 | 2.02 | 16.5 | 62.9 | 180 | 1.2 | 1.2 | 0.00 | 9.1 | 28.4% | 29.9 / 12.8 |
| navier | 41.2 | 42.2% | 17.40 | 6.88 | 18.7 | 95.0 | 172 | 2.6 | 0.0 | 0.01 | 7.6 | 11.1% | 28.8 / 11.9 |
| sha256 | 25.3 | 27.9% | 7.05 | 1.80 | 11.3 | 72.5 | 186 | 9.7 | 0.3 | 0.15 | 30.1 | 23.5% | 27.0 / 12.4 |
| json | 21.1 | 3.8% | 0.79 | 0.44 | 10.0 | 83.1 | 333 | 58.6 | 7.2 | 0.99 | 31.0 | 20.9% | 22.1 / 14.7 |
| regex | 21.0 | 31.3% | 6.58 | 1.70 | 14.4 | 93.6 | 195 | 28.5 | 8.9 | 3.27 | 33.8 | 17.3% | 22.4 / 12.8 |
| strings | 18.2 | 11.2% | 2.04 | 0.16 | 6.8 | 74.9 | 304 | 23.3 | 1.3 | 0.00 | 16.2 | 27.1% | 22.6 / 17.5 |
| dom | 19.6 | 33.6% | 6.59 | 1.92 | 13.5 | 68.4 | 293 | 33.5 | 9.9 | 3.48 | 27.4 | 28.6% | 27.0 / 13.7 |
| funcs | 17.8 | 25.5% | 4.54 | 0.75 | 7.5 | 74.7 | 212 | 6.9 | 0.1 | 0.06 | 17.8 | 40.1% | 27.9 / 18.2 |

Other facts:
- Call depth in the windows was at most 10, so a 64-entry RAS has ample margin.
- The engine's text is 1.03 MB. The interpreter function `JS_CallInternal` is 57.8 KB, and the hot
  parser functions are 10-14 KB each.
- Conditional branches are taken 34-46% of the time.

### 3.2 Ranking by expected impact on JS throughput (Judgement, reasoning given)

1. **I-cache organisation and fill path** (`rv64_ooo.sv:1638-1642, 2444-2446`; bus priority
   `architecture.md:88`). The direct-mapped 64 KiB cache with 8-byte lines misses 7-59 MPKI on
   json, regex, dom, strings, props and sha256, even though the touched code is only 8-34 KiB. Most of
   those misses are conflicts: hot interpreter, parser and runtime code spread across 1 MB aliases
   in a direct-mapped index. The cold cost of one-beat lines adds to that, since every second
   instruction is a new line.
   - With flat memory (2 clocks per beat) this costs about 10-25% of clocks.
   - In the 7-Zip deciding configuration (L2 hit 20 clocks, fetch behind every data miss on the
     bus), 30 MPKI x 20 clocks is about 600 clocks per KI. That exceeds the whole goal budget of
     about 100-140 clocks per KI, so it would dominate.
   - A 4-way cache with 64 B lines brings the same kernels to 0-3.5 MPKI.
   - This is the largest lever under realistic latency. It matches the MICRO 2015 Node finding:
     61 L1I MPKI at 32 KB.
2. **Indirect-target prediction** (`:2455-2460`). Our BTB predicts a non-return JALR from the last
   target only. That misses 0.8-17.4 times per KI, 7 on average.
   - Each miss costs at least the JALR's resolution latency plus refetch, which is about 10+ clocks
     with `FE_DEPTH` 8. At the goal's budget of about 100-140 clocks per KI, 7 MPKI x 10-15 clocks
     is 50-100% overhead.
   - An ideal path-history predictor removes 60-95% of these misses. Real ITTAGE gets close to
     that (Rohou et al.).
   - It also serves polymorphic inline-cache call sites and virtual calls in JIT code, the case
     V8's short-builtin-calls work targets.
   - It is first-ranked at the default idealised front end. Its measured weight there is not yet
     known: it is the first RTL experiment.
3. **BTB capacity and organisation** (`:165-167`). Fetch predecode already covers JAL, returns and
   backward branches. Even so, 7-19 BTB misses per KI remain, mostly forward taken branches and
   indirect jumps across a 1 MB text; a direct-mapped 1024-entry BTB is small for this code. Fix:
   a 4-8K-entry set-associative BTB, or a two-level BTB.
4. **Guards on just-loaded values (tag, shape and refcount checks).**
   - 11-40% of conditional branches use a value loaded at most 4 instructions earlier. Loads are
     22-30% of instructions and stores 12-18%; the stores are refcount updates and 16-byte JSValue
     moves.
   - Under `LD_LAT` 4 every mispredicted guard resolves 3 clocks later. The fix is predictor
     accuracy plus an L0 hit or load-latency path: the `RV64_OOO_L0_N` knob exists.
   - Value prediction (32 equal results per PC) helps monomorphic JIT shape checks, whose load PC
     sees one shape. It does not help the interpreter, where one handler PC sees many shapes.
     Measuring it on a JIT is future work.
   - A compare-and-branch fusion is not needed, because RISC-V branches compare.
5. **ISA gaps.**
   - **A** blocks every real engine: V8, JSC and their GC and compiler threads. It is not needed
     by QuickJS.
   - **C** gives smaller code for the 1 MB engine binary, which eases weakness 1. It is required to
     run distro or Node binaries.
   - **Zicond** is useful in branchless tag and select code. V8 does not probe it, so the gain is
     small.
   - **Misaligned access** is not needed by any of these engines.
   - **FENCE.I clears the whole I-cache** (`:1912`), although stores already keep the cache coherent
     (`:1896-1897`). A JIT that patches an inline cache every few thousand instructions would
     refetch all its code each time. Fix: make FENCE.I a drain plus refetch with no invalidation,
     which is safe for one hart because stores invalidate their beats. That is a PATCH and needs a
     review.
6. **No OS, MMU or privilege.** V8, JSC, Node and Bun need mmap, mprotect, threads, signals and Sv39.
   This is the C1/C3/S-track work (`build/research/isa-roadmap.md` 2.1, 2.6, 2.18).
7. **Not weak:** RAS depth (64 entries against a depth of 10 or less), store bandwidth (3 store-address
   ports and up to 4 writes per request), integer width and the direct-branch predictor (34-46% of
   branches taken, TAGE-like).

---

## 4. A benchmark small enough to optimise against

### 4.1 (a) Now: QuickJS-ng bare metal (prototype built and run)

Files are in `build/research/js/`:
- `shim/libc.c`: 51 symbols. It provides memory and string routines, a size-class allocator,
  `vsnprintf`, `strtod` through QuickJS's own `js_atod`, exact `floor`, `ceil`, `trunc`, `round`,
  `fmod`, `frexp`, `scalbn` and `lrint`, `sqrt` (with the FPU, or by exact integer recurrence in the
  soft-float build), and the soft-float conversions missing from the vendored compiler-rt subset.
  Transcendentals stop the run with a recorded reason. Time is fixed at 0, so runs are
  deterministic.
- `shim/include/`: the shim headers.
- `shim/js_bench.c`: the harness. It provides `print` (output folded into an FNV-1a hash) and
  `mark(n)` (mailbox word 0). Mailbox words: 2 "QJSBENCH", 3 hash, 4 bytes, 5 exception, 6 heap.
  The bare-metal runtime is built with `JS_NewRuntime2` so the allocator reports usable sizes as
  glibc does.
- `kernels.js`, `gen_src.py`, `link.ld` (32 MiB RAM, 1 MiB stack), `build.sh`, `profile_all.sh`,
  `analyze.py` and `native_ref.sh`.

Engine sources are compiled unmodified. The only defines are `-D__DJGPP` (no threads, no atomics,
`gettimeofday` time), `-DNDEBUG` and `-D_GNU_SOURCE`.

Kernels are original code. They are deterministic: an xorshift PRNG, no Date, no `Math.random`, no
transcendental functions. Each prints one line and is bracketed by `mark(0x10+i)` and `mark(0x30+i)`.

| # | Kernel | What it stresses | Size | RV instructions (hard float) | RV (soft float) | AArch64 instructions | RV / AArch64 |
|---|---|---|---|---:|---:|---:|---:|
| 0 | props | monomorphic and 4-way polymorphic property access, constructors, method calls (inline caches) | 3,000 iterations | 27.84M | 27.68M | 22.50M | 1.24 |
| 1 | sched | Richards-like task scheduler with 4 task classes, prototype dispatch, linked packet queues | 5,000 steps | 27.02M | 27.44M | 20.88M | 1.29 |
| 2 | navier | Float64Array diffusion and advection stencil (NavierStokes-like) | 24x24, 4 steps | 26.82M | 38.54M | 22.08M | 1.21 |
| 3 | sha256 | 32-bit integer and bit operations, Int32Array/Uint8Array, BigInt set-up | 1 KiB x 4 | 29.81M | 32.96M | 23.61M | 1.26 |
| 4 | json | JSON.stringify and JSON.parse of 400 records, then a walk | 400 records | 33.55M | 34.38M | 27.61M | 1.22 |
| 5 | regex | log-line RegExp exec, replace with a callback, global match | 400 lines | 27.05M | 27.55M | 22.69M | 1.19 |
| 6 | strings | template literals, join/split, charCodeAt, `+=`, indexOf | 400 | 46.84M | 52.24M | 38.34M | 1.22 |
| 7 | dom | DOM-like tree: build, Map/Set attributes, query by class, remove, serialise (the web-page flavour) | 800 nodes | 30.82M | 30.81M | 24.66M | 1.25 |
| 8 | funcs | closures, map/filter/reduce, sort with a comparator | 2,000 | 24.42M | 25.81M | 20.15M | 1.21 |
| | start-up + parse | JS_NewRuntime/NewContext 0.96M, script parse and compile 5.2M | | 6.16M | 6.18M | 5.92M | |
| | **total** | | | **281.3M** | **304.6M** | 228.5M | |

- **Check.** The output hash `06484b07bf7fe92f` (251 bytes) is identical on rv_iss with the hard-float
  build, on rv_iss with the soft-float rv64imb build, and natively on aarch64 (glibc malloc and libm,
  same engine sources, clang 18.1.3 -O2).
- **Cost.** rv_iss runs the whole suite in 1.7-1.8 s (about 160 MIPS).
- **Proposed port, step 1.** Add `run_bench.py --benchmark js`, modelled on `lzma` and `rt`:
  - Vendor QuickJS-ng with SOURCE.txt hashes and the shim.
  - Phases are the 9 kernel markers.
  - Measure with sampled simulation: rv_iss fast-forwards to each phase, then runs a 3M detailed
    warm-up and N pieces, as for d22. Every piece's trace is checked against rv_iss.
  - The whole-run mailbox must equal `expected.json` from the native run.
  - Per-kernel figure: kernel clocks (lower is better). Suite figure: the geometric mean of laptop
    clocks divided by our clocks.
  - Every kernel runs twice in-process and the second call is timed, so code, data and predictors
    are warm on both machines. The first call costs simulation time only through rv_iss
    fast-forward.

### 4.2 (b) Laptop reference

Preliminary probe, measured 01:35. One Cortex-X925 (vCPU 19, MIDR part 0xd85), WSL Ubuntu 24.04,
clang 18.1.3 -O2. User-space PMUv3 counters (INST_RETIRED 0x08, CPU_CYCLES 0x11) are read at each
mark; 5 pinned runs, medians.

| Kernel | Cycles (median) [min-max] | AArch64 IPC | **Proposed goal, laptop +50%: our clocks at most** | RV IPC that implies |
|---|---:|---:|---:|---:|
| props | 4,390,037 [4.32-4.52M] | 5.13 | 2.93M | 9.5 |
| sched | 5,077,138 [4.86-6.34M] | 4.11 | 3.38M | 8.0 |
| navier | 3,957,416 [3.86-5.50M] | 5.58 | 2.64M | 10.2 |
| sha256 | 4,987,267 [4.57-6.61M] | 4.73 | 3.32M | 9.0 |
| json | 5,279,734 [5.21-7.88M] | 5.23 | 3.52M | 9.5 |
| regex | 4,089,407 [4.04-4.18M] | 5.55 | 2.73M | 9.9 |
| strings | 7,020,510 [6.94-7.29M] | 5.46 | 4.68M | 10.0 |
| dom | 6,025,619 [5.95-7.43M] | 4.09 | 4.02M | 7.7 |
| funcs | 4,981,152 [4.69-5.99M] | 4.05 | 3.32M | 7.4 |

Caveats:
- These are single cold passes in a 50 ms process, and the clock had not ramped: cycles divided by
  wall time gave only 0.9-2.5 GHz. Only the cycle counts are used.
- The reference step must repeat this with the warm-second-call harness, 5 or more runs, and
  vCPU 19, plus the dependent-add clock check used for 7-Zip and ray tracing.
- Node and Bun, if installed later, are JIT context only and not the same algorithm. Neither is
  installed in WSL now (Fact: `which node bun` found nothing). I did not install them, because this
  task allowed no binary downloads.
- **Judgement:** the goal is aggressive. The X925 already runs this interpreter at an IPC of 4-5.6,
  and RISC-V needs 1.19-1.29x more instructions: there is no load or store pair, and every 16-byte
  JSValue move is two loads and two stores.

### 4.3 (c) Later: JIT on RISC-V

1. **User-mode checkpoint replay** (Judgement, an intermediate step):
   - Run Node (V8 with Sparkplug, Maglev and TurboFan) on riscv64 Linux in QEMU.
   - Snapshot a user process between syscalls: registers plus the touched pages.
   - Replay the snapshot on our core until the first ECALL, which stops the run, as rv_iss does.
     JIT-hot loops run millions of instructions without a syscall.
   - Needs: **C and A** (Node binaries are rv64gc), F/D (0.17.0), a sparse 64-bit memory in the
     testbench, and identity-mapped user addresses. No MMU is needed.
   - This would measure real V8 JIT code (inline caches, deopt checks, write barriers) years before
     Linux runs on the core.
2. **Full stack:** M, S and U modes, Sv39, interrupts and timers (ACLINT/Sstc), A, C, Zicntr, then
   Linux, then Node (Experimental tier) and later JSC. It is the isa-roadmap's S track.
   JetStream 3 and Speedometer 3 (https://browserbench.org) need a browser and are out of reach;
   use their JS kernels standalone.

---

## 5. Plan (ordered; each step is its own version or experiment per AGENTS.md)

Expected gains are Judgement, from the trace statistics. Each needs an RTL measurement before it is
claimed.

| # | Step | Kind | Expected JS effect | Risk to 7-Zip / Dhrystone |
|---|---|---|---|---|
| 1 | Port the benchmark: `--benchmark js` with vendored QuickJS-ng v0.18.0 (provenance, hashes), shim libc, kernels, the warm second-call timing, the native `expected.json` and sampled RTL. First RTL numbers on 0.16.2 (soft float) and 0.17.0 (`--fpu`), flat and deciding configuration, at both cache sizes | experiment, no version (bench and test only) | baseline | none |
| 2 | Laptop reference with the final harness, 5+ pinned runs, cycle counter checked | experiment | — | none |
| 3 | Goal proposal to the user: laptop +50% per clock, per kernel and geometric mean (propose only; the user sets it) | decision | — | — |
| 4 | Front-end profile on RTL: probe counters for indirect mispredicts, I-cache misses, BTB misses and fetch-stall clocks per kernel (backend-style probe, gated to sample windows) | experiment | measures the weights of ranks 1-3 | none |
| 5 | **Indirect-target predictor**: ITTAGE-style tagged tables over path history (targets as offsets, as the BTB stores them), trained at retirement and repaired with the global history | PATCH (microarchitecture) | removes 60-95% of the 7 average indirect MPKI; estimated 10-30% fewer clocks at `FE_DEPTH` 8, less at 0 | low: 7-Zip and Dhrystone have few indirect jumps; state cost about 10-20 KiB |
| 6 | **I-cache: set associativity, 64 B lines, critical-beat-first fill, next-line prefetch**, and fetch misses not behind every data read | PATCH (cache geometry), or MINOR if the bus or fill contract changes (several beats per fill) | 7-59 MPKI down to 0-3.5 at 64 KiB; 10-25% flat, more than 2x in the deciding configuration | medium: longer fills compete with data misses on one bus. 7-Zip and Dhrystone code is small, but the 4 KiB Dhrystone figure changes. Run both cache sizes |
| 7 | **BTB**: 4-8K entries, set-associative, or a two-level micro-BTB plus BTB | PATCH | 7-19 misses per KI down; about 5-10% | low |
| 8 | FENCE.I as drain plus refetch with no I-cache clear (stores already invalidate beats) | PATCH, after Codex review | none on QuickJS; large for a future JIT that patches inline caches; needs a JIT-like test (code writes, then FENCE.I loops) | low; must keep the self-modifying-code tests |
| 9 | Load-latency path for guards: measure the L0 (`RV64_OOO_L0_N` 16) and `LD_LAT` 4 on the JS kernels; consider value prediction confidence per PC and global history (shape values) | experiment, then PATCH | unknown; the guard share (11-40%) says measure it | already a deciding-config knob |
| 10 | **Zicond** (`czero.eqz/nez`) with a clang `-march` A/B on QuickJS | MINOR (contract) | small (1-3%, Judgement) | none (an option) |
| 11 | **C (Zca, then Zcb)**: about 25% smaller code, eases ranks 1 and 3; needed for distro binaries | MINOR | 3-10% under realistic I-cache latency | medium: 16-bit fetch alignment touches fetch, predecode, fusion and folding (isa-roadmap 2.8) |
| 12 | **A (Zaamo, Zalrsc)** single-hart, atomic at retirement | MINOR | none on QuickJS; prerequisite for V8, JSC, Node and Bun | low |
| 13 | User-mode checkpoint replay of Node/V8 (section 4.3) | experiment (testbench change) | first real JIT measurements | none |
| 14 | Privilege, Sv39, timers, Zicntr, Linux, Node | MAJOR track | full stack | high, long |

Order rationale: measure first (1-4). Then the two front-end items that the traces already point to
(5, 6), with indirect prediction first because it is isolated from the bus contract. Then capacity
(7). Then ISA steps that are prerequisites for real engines (10-12). Each step runs the JS suite plus
the 7-Zip and Dhrystone regressions at both cache sizes, as AGENTS.md requires.

---

## 6. Experiments run (DEVLOG rows for the coordinator)

All in `build/research/js/`, uncommitted, repository HEAD `e8eeae3` to `c607485`. Tools: WSL Ubuntu
24.04 aarch64, Ubuntu clang 18.1.3 and LLD 18.1.3, Python 3.12.3, rv_iss from the working tree's
`sim/cpu/bench/rv_iss.c` (blob 17e0a038) built with `clang -O2 -std=c11`. Every run was under
`timeout 300` or less.

| Time | Goal | Commands | Result | Conclusion |
|---|---|---|---|---|
| 01:18 | Fetch QuickJS-ng from its official release | `curl -sSL -o quickjs-ng-v0.18.0.tar.gz https://github.com/quickjs-ng/quickjs/archive/refs/tags/v0.18.0.tar.gz`; `sha256sum`; GitHub API ref lookup | 910,210 bytes, SHA-256 28bcd89a...f9f1dd, tag v0.18.0 = commit d7215b0a | source only, in the ignored `build/research/js/src` |
| 01:19 | Does the engine build bare metal for rv64imfd? | `clang --target=riscv64-unknown-elf -march=rv64imfd_zba_zbb_zbs -mabi=lp64d -O2 -nostdinc -isystem <resource>/include -isystem shim/include -D__DJGPP -DNDEBUG -D_GNU_SOURCE -mcmodel=medany -c` on quickjs.c, libregexp.c, libunicode.c and dtoa.c; `llvm-nm` | all 4 compile unmodified (text 1.00 MB); **51** unresolved libc symbols | a small shim libc suffices |
| 01:24-01:25 | First end-to-end run, scale 1 | `build.sh 1`; `rv_iss --ram 33554432 --image bench.bin --fp 1 --mailbox 1ffff00`; native `qjs_bench` | 617.5M RV instructions, EBREAK, exception 0; hash 8528185cba93e4f0 equal to native | works; kernels too large (props 183M, strings 174M) |
| 01:26 | Surprise check: props costs 9K instructions per iteration | 1M-instruction trace (`--trace-from 50000000`), function profile | 54% JS_CallInternal, plus shape and property-add functions; with the usable-size fix (JS_NewRuntime2) counts unchanged | engine behaviour, not a port bug |
| 01:27 | Native instruction and cycle counts | harness reads PMUv3 0x08 and 0x11 with perf_event_open; `taskset -c 19` | RV / AArch64 instructions 1.19-1.29; X925 IPC 4.1-5.7 | RV code is about 1.24x longer |
| 01:27 | Rescale kernels to about 25-45M | edited the `kernels.js` sizes; `build.sh 1`; rv_iss | 281,314,701 instructions; per kernel 24.4-46.8M; hash 06484b07bf7fe92f equals native | sizes adopted |
| 01:28-01:30 | Front-end and cache statistics per kernel | `profile_all.sh` (rv_iss `--trace` 1.5M window per kernel, `analyze.py` with 0.3M warm-up) | the table in section 3.1. Two failed first attempts: rv_iss inside `while read` consumed the window list (fixed with `</dev/null`), and `analyze.py` shadowed its path argument (fixed) | evidence for the ranking |
| 01:31-01:36 | Soft-float rv64imb build for the released cores | `ISA=rv64im_zba_zbb_zbs_zifencei ABI=lp64 SOFTFP_OBJS=<vendored compiler-rt built to crt-imb/> build.sh 1` | first link needed __fixdfsi, __fixunsdfdi, __fixunsdfsi, __truncdfsf2 and round (added to the shim). First run **hung**: my __fixunsdfdi called compiler-rt's __fixdfdi, which calls __fixunsdfdi (mutual recursion); killed by `timeout 300`. Fixed with a standalone bit version: 304,595,994 instructions, hash 06484b07bf7fe92f equals native | runs on the released 0.16.2 ISA; soft float +8% (navier +44%) |
| 01:35 | Preliminary laptop reference | `native_ref.sh` (5 runs, `taskset -c 19`) | per-kernel cycles in section 4.2; clock not ramped (0.9-2.5 GHz effective) | provisional; redo with warm second calls |

No RTL simulation was run: no Verilator or Icarus, and nothing under `sim/` was invoked except
compiling `rv_iss.c` and assembling `start.S` from their repository paths.

## 7. Caveats

- The cache, BTB and indirect figures come from trace models (`analyze.py`), not from the RTL. The
  path-history model is an unbounded ideal. The data cache is not modelled, because rv_iss traces
  carry store addresses but not load addresses.
- The native reference uses glibc malloc, the bare-metal build the shim allocator. Both execute the
  same JS work, and the checksums prove the same results. Allocator speed is part of each figure,
  as memcpy is for 7-Zip.
- QuickJS is an interpreter-only engine. It is a stand-in for Ignition, LLInt and jitless modes, not
  for JIT tiers. Its 16-byte JSValue differs from V8's compressed and JSC's NaN-boxed values. JIT
  conclusions need step 13.
- Web facts come from sub-agents' reading of official sources at the pinned commits. Some files were
  read only in parts: misaligned-access needs and rdcycle use in V8 are marked Judgement. Rohou et
  al. is cited second-hand. No published per-clock JS comparison across CPUs was found.
