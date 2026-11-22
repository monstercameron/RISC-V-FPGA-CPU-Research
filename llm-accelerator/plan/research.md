# Custom RISC-V CPU on FPGA — research notebook

Current accelerator decisions are in [plan.md](plan.md), [implementation-contract.md](implementation-contract.md), [abi-v1.md](abi-v1.md) and the [adversarial review](refinement-review.md). Earlier CPU, board-discovery and FFN material below is historical research; it does not override these contracts.

Research date: 23 October 2026. This document combines five Luna research tracks using official specifications, project repositories, and vendor documentation. Recommendations are engineering judgments for a first custom core; they are not measured results for a completed design. Prices, inventory, licensing, and supported devices should be rechecked before purchase or installation.

## Recommended starting point

Build a handwritten, multicycle, 32-bit RV32I core in synthesizable SystemVerilog. Begin with a documented bare-metal execution environment, on-chip instruction/data memory, a single clock, and a simple memory interface. Add UART and GPIO for the first board demonstration. Make memory requests tolerate wait states from the beginning so synchronous FPGA block RAM fits naturally.

Use Verilator and cocotb for automated simulation, a waveform viewer for diagnosis, and a RISC-V GNU bare-metal compiler targeting the exact implemented ISA and ABI. On this Windows workstation, WSL2 is a sensible home for the Linux-oriented simulation/compiler tools; select a supported native Windows or Linux installation for the FPGA vendor tools. Decide USB programming and file handoff explicitly.

Choose the board/tool flow together. Shortlist ECP5/ULX3S for an open implementation flow and Artix-7/Arty A7 for a vendor-supported learning ecosystem. Existing hardware, budget, and availability can change that choice. iCE40 is useful for very small cores; it offers less growth room. The detailed board comparison below explains the alternatives.

Keep the CPU datapath and control logic your own. Use existing cores as references or comparison targets, and reuse well-understood peripherals, interconnect, and board infrastructure where useful. A CPU core is only one part of the SoC that actually runs a program.

## Reading map

1. Languages and synthesis/toolchain choices.
2. ISA specifications and software tools.
3. Reference cores, reusable IP, and buses.
4. Simulation, verification, and debugging.
5. FPGA families and board choices.
6. Implementation milestones and decisions to record.

Links in each research track point to the supporting primary sources. Pin specification editions, repository commits, and tool versions when implementation begins; moving documentation and development branches are discovery sources rather than reproducible project dependencies.


---

## HDL and toolchain choices for a beginner RISC-V FPGA core

Research snapshot: 23 October 2026. The recommended first project is a small, single-issue RV32I core in synthesizable SystemVerilog, with simulation and lint before board integration. Keep the first version portable: simple synchronous memories, explicit reset/clock, no vendor primitives until needed. If the goal is primarily to learn processor design and the selected board has a supported open flow, plain Verilog/SystemVerilog plus Yosys and nextpnr keeps the toolchain inspectable. If the board is AMD or Intel, use its vendor implementation tools for final timing and bitstream generation.

### Language comparison

| Choice | What it gives you | Practical tradeoff for this project |
|---|---|---|
| SystemVerilog | Standardized Verilog successor with RTL, types/structures/enums, assertions and verification constructs (IEEE 1800-2023). | Best default for a first handwritten core: readable RTL, broad vendor support, and lots of reference material. Use the synthesizable subset; simulation-only features are not hardware. Vendor and open-source frontends do not support every standard feature equally. |
| Verilog | Mature, compact RTL; broad tools and legacy designs. | Good if following a Verilog-first course or using a constrained open tool. SystemVerilog improves type safety and clarity for decode/control logic with enums and `always_comb`/`always_ff`; choose SV unless a toolchain requires Verilog-2005. |
| VHDL | Strongly typed, explicit RTL language with mature vendor synthesis. | Equally viable, especially in VHDL-oriented courses or existing designs. It is more verbose for a small core and the free open-source flow is less turnkey: Yosys's standard frontend is chiefly Verilog; GHDL integration is an additional path. |
| Chisel | Scala-embedded hardware construction language that builds parameterized generators and emits synthesizable Verilog; uses the FIRRTL/CIRCT compiler ecosystem. | Excellent once you want reusable, parameterized generators or Scala is already familiar. It introduces Scala/build/compiler concepts before basic RTL and the CPU's emitted RTL still needs the FPGA vendor/open synthesis flow. |
| SpinalHDL | Scala-based RTL language with checks and generation of Verilog, VHDL, or SystemVerilog. | An approachable generator route if Scala appeals, with easy handoff to normal EDA tools. Setup includes Java/Scala and a build tool; generated output is an extra layer to inspect. Core compiler is LGPL-3.0; library and other components are MIT, so check component licenses if redistributing the toolchain. |
| Amaranth | Python-based synchronous hardware language, simulator and FPGA build system; can emit RTL and drive several supported toolchains. | Attractive for Python users and quick experiments, with a high-level board/build workflow. It adds Python elaboration semantics and platform-specific support must be checked against the exact board. Amaranth itself is BSD-2-Clause. |

A custom CPU is a good place to learn RTL directly. Generator HDLs help when the design needs many configurations; they do not remove the need to understand cycles, interfaces, reset behavior, timing, or generated RTL. They are not HLS: these describe hardware structures and generate RTL.

### Toolchain and board constraints

- **AMD FPGA:** Vivado synthesis officially accepts SystemVerilog, Verilog, VHDL, and VHDL-2008, but only supported synthesizable constructs. The 2026.1 release introduced a tiered licensing model; BASIC is free with annual renewal and supports Windows/Linux, while device/feature support depends on tier. Check the exact FPGA part before buying a board or committing to Vivado. Packaging custom IP has an extra wrapper restriction for SystemVerilog and VHDL-2008 top-level files; ordinary project synthesis is broader.
- **Intel/Altera FPGA:** Quartus integrated synthesis supports VHDL, Verilog and SystemVerilog. Supported language versions/features depend on the Quartus edition and release; use `.sv` files for SystemVerilog constructs and check the release's synthesis guide. Mixed-language simulation can require a mixed-language simulator or Questa edition.
- **Open-source route:** Yosys has extensive Verilog-2005 and partial SystemVerilog support. `yosys-slang` adds a broader SystemVerilog frontend, while YosysHQ's commercial Tabby CAD suite includes Verific for industry-grade SystemVerilog/VHDL frontend coverage. Do not assume all SystemVerilog syntax or assertions work in the standard Yosys frontend. nextpnr is open-source place-and-route, but support is architecture-specific: stable routes include Lattice iCE40/ECP5 and several community-supported families; Cyclone V and some others are explicitly experimental. Confirm that the selected chip has synthesis, place/route, bitstream, and programming support, not just RTL parsing.
- **Licensing:** Yosys uses the ISC license; nextpnr is open source (its repository contains the applicable COPYING terms). Chisel is Apache-2.0; Amaranth BSD-2-Clause; SpinalHDL has split core/library licenses as above. Vendor FPGA tools are governed by vendor license tiers and device entitlements. These tool licenses are separate from the RISC-V ISA specifications and from any third-party core IP license.

### Suggested learning path

1. Write a tiny combinational/sequential block and testbench in SystemVerilog; learn bit widths, signedness, blocking versus nonblocking assignments, clocked state, and reset.
2. Build a multicycle RV32I core with a deliberately small instruction subset first. Keep instruction decode, register file, ALU, control FSM, and memory interface as separate modules.
3. Simulate directed instruction tests and compare architectural state against a reference model; then add a documented bus/memory contract and constraints.
4. Run synthesis for the exact FPGA family, inspect inferred memories and utilization, then place, route, and test on the board. Preserve a portable RTL core and isolate vendor-specific clock, RAM, and pin details in wrappers.

#### Sources (official or primary documentation)

- IEEE, [IEEE 1800-2023 SystemVerilog standard overview](https://standards.ieee.org/ieee/1800/7743/).
- AMD, [Vivado Design Entry & Implementation](https://www.amd.com/en/products/software/adaptive-socs-and-fpgas/vivado/implementation.html), [Vivado 2026.1 synthesis guide](https://docs.amd.com/r/en-US/ug901-vivado-synthesis), [2026.1 licensing options](https://www.amd.com/en/products/software/adaptive-socs-and-fpgas/vivado/vivado-licensing-options.html), and [custom IP top-level requirements](https://docs.amd.com/r/en-US/ug1118-vivado-creating-packaging-custom-ip/Top-Level-HDL-Requirements).
- Intel/Altera, [Quartus supported HDL synthesis overview](https://www.intel.com/content/www/us/en/support/programmable/support-resources/design-guidance/quartus-support.html), [supported language standards](https://www.intel.com/content/www/us/en/docs/programmable/683870/24-1/supported-hardware-description-languages.html), and [VHDL synthesis support](https://www.intel.com/content/www/us/en/docs/programmable/683236/22-4/vhdl-synthesis-support.html).
- YosysHQ, [Verilog support notes](https://github.com/YosysHQ/yosys/blob/main/docs/source/using_yosys/verilog.rst), [Yosys overview](https://github.com/YosysHQ/yosys/blob/main/docs/source/introduction.rst), and [nextpnr supported architectures and setup](https://github.com/YosysHQ/nextpnr).
- Chisel, [introduction](https://www.chisel-lang.org/chisel3/), [quick installation and Verilog emission](https://www.chisel-lang.org/docs/installation), [project repository and license](https://github.com/chipsalliance/chisel).
- SpinalHDL, [overview and licensing](https://github.com/SpinalHDL/SpinalHDL), [installation/tool requirements](https://spinalhdl.github.io/SpinalDoc-RTD/master/SpinalHDL/Getting%20Started/Install%20and%20setup.html), and [HDL generation](https://spinalhdl.github.io/SpinalDoc-RTD/master/SpinalHDL/Other%20language%20features/vhdl_generation.html).
- Amaranth, [language/toolchain and FPGA platform list/license](https://github.com/amaranth-lang/amaranth), [toolchain introduction](https://amaranth-lang.org/docs/amaranth/v0.5.5/intro.html).

---

## RISC-V ISA and software plan for an FPGA CPU

Research checked 23 October 2026. Prefer the ratified specifications library over draft branches. Its current official release is January 2026 (v20260120), with a per-module ratification/version table; the older 20240411 release remains useful when comparing. “Latest manual release” and the version number of an individual ISA module are different things.

### Specification baseline

The official [unprivileged ISA library](https://docs.riscv.org/reference/isa/) covers user-visible instruction behavior and extensions. RV32I is ratified version 2.1; its instructions are 32 bits and IALIGN=32. C changes instruction alignment to 16-bit (IALIGN=16). The [current privileged volume](https://docs.riscv.org/reference/isa/priv/priv-index.html) is release 20260120 and identifies the machine and supervisor ISA modules as version 1.13; its modules and status are itemized in the [preface](https://docs.riscv.org/reference/isa/v20260120/priv/priv-preface.html). M-mode is the only required privilege mode; U and S are optional. M-mode is the first mode entered at reset. A bare-metal CPU can therefore be a valid minimal M-mode implementation without implementing an OS, virtual memory, S-mode, or a debug module.

Useful module versions for the minimal progression: RV32I 2.1, M 2.0, C 2.0, Zicsr 2.0, Zifencei 2.0. The [Zicsr chapter](https://docs.riscv.org/reference/isa/v20260120/unpriv/zicsr.html) explains why CSR instructions are now a separate extension: counters and timers are no longer mandatory parts of base ISA. Do not infer that implementing CSR instructions means implementing every CSR, timer, counter, interrupt source, or privileged feature.

### Practical implementation progression

1. **RV32I** is the clean teaching/core baseline: 32 integer registers (x0 hardwired zero), base integer arithmetic/logical operations, branches/jumps, and byte/halfword/word loads and stores. Implement all normative semantics and exceptions, not just opcodes that happen to appear in a hello-world program. Toolchain target: `-march=rv32i -mabi=ilp32`.
2. **Add M** for hardware multiply/divide if desired. It is a relatively self-contained integer extension, conventionally spelled `rv32im`. Compilers otherwise may emit helper calls for arithmetic, depending on runtime/toolchain configuration.
3. **Add C** when code density matters. `rv32imc` permits 16-bit instructions, changes IALIGN to 16, and expands fetch/decode/alignment cases. Test instruction fetch across word/bus boundaries. C is not required for C-language support.
4. **Add Zicsr** when firmware needs `csrr*`/`csrw*` to manipulate architectural control/status registers. Assembly with CSR mnemonics needs `-march=..._zicsr`; choose and document the actual supported CSR set. `Zicsr` supplies the access instructions, not a blanket mandate to implement all CSR addresses.
5. **Add Zifencei** if software needs `fence.i` to make prior stores to instruction memory visible to subsequent fetches (e.g. code download/JIT). For a fixed ROM/FPGA program with no self-modifying or downloaded code, defer it. It is separate from base `FENCE`, which orders memory accesses. A common fuller target is `rv32imc_zicsr_zifencei`; use `-mabi=ilp32`.

Use explicit versioned ISA strings when reproducing historical builds or compliance results. For contemporary GCC/LLVM, select only implemented extensions; “G” expands to a much larger bundle (including F/D and Zicsr/Zifencei in newer spec naming), and is unsuitable as shorthand for a small integer-only core.

### Traps, memory and CSR boundaries

A minimal core still needs defined instruction and data behavior: legal/illegal instruction handling; ECALL/EBREAK behavior as applicable; taken control-transfer alignment; load/store alignment; and the execution environment's address map and access-fault behavior. RV32I leaves some execution-environment details to the platform. In particular, misaligned data access may be handled invisibly, completed, or trapped according to the execution environment; pick one policy, document it, and make hardware and tests agree. Do not assume every misaligned access must be transparently supported by the ISA. With I only, a taken branch/jump to an address not divisible by four raises instruction-address-misaligned; with C, halfword alignment is sufficient.

If implementing privileged M-mode, implement the applicable machine trap/return semantics and the machine CSRs actually needed by the platform (commonly `mstatus`, `mtvec`, `mepc`, `mcause`, and `mtval`, with `mie`/`mip` only if interrupts are implemented). An exception is synchronous; an interrupt is asynchronous. `MRET` and trap entry semantics are privileged architecture, not ordinary RV32I. The exact optional CSR fields and WARL/WLRL behaviors must follow the privileged module. A tiny firmware environment may avoid interrupts and use a controlled fatal handler; still define reset PC, trap vector, and termination/debug conventions.

Memory map, reset address, ROM/RAM sizes, MMIO side effects, timer/interrupt controller, console, and test pass/fail mechanism are platform/EEI contracts, not determined by choosing RV32I. A linker script and startup code must match them. “Bare metal” is not itself an ISA privilege mode. An FPGA core can expose only M-mode and a simple MMIO map. Debug module/JTAG/Debug Spec is separate from M/S/U privilege and not required to execute normal firmware.

### ISA versus ABI and firmware build

ISA answers which instructions and architectural behavior exist. ABI answers how separately compiled code interoperates: data type sizes, register roles, stack alignment, argument/return passing, ELF metadata and relocation conventions. For RV32I, the standard integer ABI is **ILP32**: 32-bit `int`, `long`, and pointers, integer calling convention, soft-float ABI. The [ratified ABI specification](https://docs.riscv.org/reference/abi/) lists ILP32 as ratified and explains named ABI/float conventions. A core can implement M while still use ILP32; ISA extension and ABI are independent selections. `ilp32f`/`ilp32d` need corresponding floating-point ISA and ABI register conventions; avoid these for an integer-only CPU.

For firmware use a bare-metal cross toolchain (GNU `riscv64-unknown-elf-*` prefix is common even when targeting RV32) or Clang/LLVM. The [GNU toolchain](https://github.com/riscv-collab/riscv-gnu-toolchain) supports Newlib/Picolibc bare-metal builds and `--with-arch=rv32i --with-abi=ilp32`; individual invocations can also set `-march` and `-mabi`. Clang documents equivalent `-march` and `-mabi` controls in its [RISC-V target guide](https://llvm.org/docs/RISCVUsage.html). Start with assembly-only bring-up, then freestanding C: `-ffreestanding -nostdlib -nostartfiles -march=rv32i -mabi=ilp32`, custom linker script (`-T`), startup assembly that establishes `sp`, initializes `.data`/`.bss` if used, and enters `main`; provide any needed `mem*` routines and compiler runtime (`libgcc` or compiler-rt) deliberately. A linker script must describe actual ROM/RAM/MMIO and entry point; libraries do not supply board-specific startup automatically. Inspect ELF and disassembly with matching `objdump`/`readelf` to catch unintended extensions and placement.

Use the same `-march` and `-mabi` for every translation unit and assembler object. ABI compatibility does not imply ISA support: two ILP32 objects may have different instruction requirements. Conversely, changing ABI changes interoperability even if both binaries use RV32I instructions.

### Reference models and tests

Use the official [Sail RISC-V formal model](https://github.com/riscv/sail-riscv) as an executable semantics/reference where supported, and [Spike](https://github.com/riscv-software-src/riscv-isa-sim) as a practical functional ISA simulator. Both help compare retirement state/traces; neither proves RTL correctness. Run directed tests and randomized verification for pipeline hazards, reset, memory timing, bus faults and interrupts.

RISC-V International's [Architectural Compatibility Tests (ACT)](https://github.com/riscv/riscv-arch-test) are assembly tests intended to check normative architectural rules, not a complete processor verification suite. Current ACT4 requires a UDB configuration describing supported extensions/parameters, DUT macros (console, terminate, interrupt hooks as needed), and a linker script for the DUT memory map; user runs generated ELF tests on the DUT/testbench. The project explicitly says extra verification is required. Do not treat an ACT pass as proof of all microarchitectural corner cases or as a complete privileged/platform test. Keep tests partitioned by declared ISA/extensions and privilege support, so unsupported instructions are not mistaken for CPU bugs.

### Primary sources

- [RISC-V Ratified Specifications Library, current landing page](https://docs.riscv.org/) and [unprivileged volume](https://docs.riscv.org/reference/isa/).
- [RV32I 2.1 chapter](https://docs.riscv.org/reference/isa/v20260120/unpriv/rv32.html), [M 2.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/m-st-ext.html), [C 2.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/c-st-ext.html), [Zicsr 2.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/zicsr.html), [Zifencei 2.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/zifencei.html).
- [Privileged volume index and preface](https://docs.riscv.org/reference/isa/priv/priv-index.html), [machine ISA](https://docs.riscv.org/reference/isa/priv/machine.html), [privilege introduction](https://docs.riscv.org/reference/isa/priv/priv-intro.html).
- [Ratified ABI library](https://docs.riscv.org/reference/abi/), [GNU toolchain](https://github.com/riscv-collab/riscv-gnu-toolchain), [LLVM RISC-V guide](https://llvm.org/docs/RISCVUsage.html).
- [Sail model](https://github.com/riscv/sail-riscv), [Spike simulator](https://github.com/riscv-software-src/riscv-isa-sim), [ACT4 tests](https://github.com/riscv/riscv-arch-test).

---

## Reusable IP and reference cores for a custom RISC-V FPGA CPU

Research checked 23 October 2026. Repository status and licenses can change; pin exact commits and inspect the license files shipped with the chosen revision before release.

### Recommendation in brief

If the central goal is to **design and own a CPU**, implement the pipeline, register file, decoder, ALU, control/status registers, traps, and memory interface yourself. Reuse software toolchains, ISA tests, verification frameworks, bus fabrics, and mundane peripherals. Treat third-party cores as executable references and differential-test targets. Track the source and license of any RTL you reuse.

If schedule or firmware compatibility matters more than CPU authorship, reuse a permissively licensed core and be explicit about that in the project: PicoRV32 is the shortest path to a small Verilog CPU with Wishbone or AXI4-Lite, while Ibex offers stronger verification and a broader debug ecosystem. LiteX is a useful SoC construction/reference environment, but adds a Python/Migen-based generator and bus/software conventions. For an educational CPU with a conventional bus, PicoRV32 is an especially useful comparison point; for this project, keep your custom CPU implementation as the primary design.

### Candidate CPU cores

| Core | Officially documented strengths and interfaces | License and practical fit |
|---|---|---|
| [PicoRV32](https://github.com/YosysHQ/picorv32) | Small, synthesizable Verilog; configurable RV32E/I/IC/IM/IMC; native valid/ready memory port, and supplied Wishbone-master and AXI4-Lite-master variants. The repo includes PCPI extensions and a basic example SoC, `picosoc`. It is intended as an auxiliary/small FPGA CPU. | ISC. Very permissive and easy to study/integrate. The upstream repository now identifies itself as archived/read-only (archived 8 Sep 2026) and says it is no longer actively developed, so pin a known revision and own any maintenance. Best reference for simple bus integration; poor choice if the project claims its processor RTL as original. [README](https://github.com/YosysHQ/picorv32/blob/main/README.md) |
| [Ibex](https://github.com/lowRISC/ibex) | Small RV32 core with substantial verification; configurable ISA/performance options and FPGA-oriented register-file implementation. Integrates with lowRISC/OpenTitan primitives and has a corresponding demo SoC with memory, GPIO, UART, timer, debug module, SPI, and physical JTAG pins. CPU alone is not a complete board SoC. | Apache-2.0 unless a file says otherwise; repository includes LICENSE and NOTICE. Strong candidate where upstream verification and debug support outweigh the integration/tooling overhead. SystemVerilog and dependencies may take more setup than a one-file Verilog core. [README/license](https://github.com/lowRISC/ibex) · [Ibex demo system](https://github.com/lowRISC/ibex-demo-system/blob/main/rtl/system/ibex_demo_system.sv) |
| [CORE-V CV32E40P](https://github.com/openhwfoundation/cv32e40p) | Four-stage in-order RV32 core with standard and PULP extensions; instruction and load/store interfaces use OBI. It has execution-based core debug support, but requires an external Debug Module and Debug Transport Module to provide the complete JTAG-to-GDB system. Its verification environment lives in the separate `core-v-verif` repository. | Solderpad Hardware License v2.1, commonly expressed as Apache-2.0 WITH SHL-2.1; check per-file headers and bundled dependencies. Good mature core/reference for OBI and performance-oriented RV32, but OBI adapters and extension/toolchain configuration add work. [Introduction](https://cv32e40p.readthedocs.io/en/latest/intro.html) · [debug manual](https://cv32e40p.readthedocs.io/en/latest/debug.html) · [license guidance](https://github.com/openhwfoundation/cv32e40p/blob/master/CONTRIBUTING.md) |
| [VexRiscv](https://github.com/SpinalHDL/VexRiscv) | FPGA-friendly, plugin-configurable RV32 implementation generated from SpinalHDL/Scala. Supports AXI4, Avalon, and Wishbone; optional debug, caches, interrupts, privilege modes, and other features. There are example SoCs and a documented OpenOCD/GDB/JTAG workflow. | MIT. Highly flexible, but the generator and plugin model mean that understanding/building the design requires Scala/SpinalHDL as well as HDL. A generated Verilog snapshot is still derived from the MIT-licensed project. [README](https://github.com/SpinalHDL/VexRiscv) · [license](https://github.com/SpinalHDL/VexRiscv/blob/master/LICENSE) |
| [SERV](https://github.com/olofk/serv) | Bit-serial RV32 core optimized for tiny logic footprint; Wishbone-like bus with a reduced set of signals. Its reference Servant SoC runs Zephyr and has broad FPGA board support. Extremely useful to study area/speed tradeoffs and minimal bus adaptation. | ISC. Excellent tiny-core/reference target, but bit-serial operation has very low throughput and the bus is only “kind of Wishbone”; do not assume drop-in Wishbone compatibility. The repo notes a UART in its Zephyr setup is bit-banged and baud depends on CPU clock. [README](https://github.com/olofk/serv) |
| [Rocket Chip](https://github.com/chipsalliance/rocket-chip) | Chisel/Scala generator for Rocket and a substantial SoC ecosystem. Uses TileLink internally, with AMBA AXI4/AHB-Lite/APB packages and converters. Better suited to generated, scalable SoCs than a small custom educational core. | Mixed licensing: repository has Berkeley, SiFive, and JTAG license files. Do not summarize it as uniformly Apache/MIT; inspect the license applying to each used source and its dependencies. Consider only if the project is intentionally building on the Rocket/Chisel ecosystem. [README](https://github.com/chipsalliance/rocket-chip) |
| [CVA6](https://github.com/openhwfoundation/cva6) | Application-class configurable RV32/RV64 core with caches, optional MMU/FPU/PMP, and AXI interface. Its specification says the core does not include items such as CLINT/PLIC or external debug module. It is much larger in scope than a simple FPGA CPU project. | Solderpad v2.1 or Apache-2.0 option is declared in official requirements; verify actual RTL and dependencies. Better as a serious high-performance subsystem/reference than as a starting point for an original small CPU. [requirements specification](https://github.com/openhwfoundation/cva6/blob/master/docs/02_cva6_requirements/cva6_requirements_specification.rst) |

#### IP provenance

Record source repositories and commits, preserve required notices, and check licenses for copied RTL, generated output, and dependencies. A peripheral, CPU core, and generator can have different licenses.

### Buses and SoC integration

A CPU memory interface, an interconnect, and peripheral register buses are separate design decisions. Keep the CPU-facing load/store interface simple and stable, then bridge it to a system fabric if useful. For a first single-hart FPGA system, one outstanding transaction at a time is often enough.

- **Wishbone** is a practical lightweight shared bus, especially in open FPGA projects and LiteX. PicoRV32 and VexRiscv provide Wishbone options. Specify the exact Wishbone revision/handshake, address units, byte enables, response/error behavior, and timeout policy. SERV’s reduced bus resembles Wishbone but is not automatically a compliant Wishbone master.
- **AXI4-Lite** is useful for memory-mapped control and bridges to FPGA vendor IP; it has separate address and data channels and response handshakes. PicoRV32 supplies an AXI4-Lite master. Do not confuse it with full AXI4, which supports bursts and is used for higher-throughput memory. A CPU whose own memory transactions are simple may use a bridge to the vendor/system AXI fabric.
- **APB** is a low-complexity peripheral bus, commonly placed behind an AXI/AHB/Wishbone bridge. It is usually a subordinate-side peripheral bus, not the best direct CPU memory protocol. The official Rocket Chip source includes APB generation/conversion support. Choose APB only if the fabric/board IP already uses it.
- **OBI** is the split instruction/data interface used by CV32E40P. It is a reasonable reference protocol, but a custom CPU will need a small OBI-compatible adapter if its native port differs.

Whichever protocol is selected, define alignment, endianness, byte strobes, misaligned access policy, instruction/data concurrency, address map, wait states, reset values, and access faults before coding peripherals. A CPU that allows fetch and data traffic concurrently needs either separate ports, arbitration, or an interconnect with multiple masters. FPGA block RAM usually has synchronous reads and limited ports, so its latency and byte-write behavior must match the CPU handshake.

### Peripherals, boot, and debugging

Keep initial hardware small: block RAM or ROM, a memory-mapped UART, GPIO/LEDs, and a timer/interrupt source. Establish a linker script and a way to load firmware before adding caches or DMA. A UART is especially useful because it gives a low-friction way to report reset, trap, and test status. Reusing a UART RTL block is sensible; document its source/license, clock/baud configuration, register map, and byte-lane behavior. LiteX provides UART/console infrastructure and configurable SoC integration; Ibex’s demo is a concrete example including UART, GPIO, timer, SPI, and debug wiring.

JTAG pins alone do not provide a usable RISC-V debugger. A working external-debug chain needs the core’s debug-entry/halt/resume support, a Debug Module, a Debug Transport Module (often JTAG DTM), DMI connectivity, reset/clock wiring, and debugger software configuration. The RISC-V Debug Specification says the DM handles abstract access and hart control while the DTM provides transport; it intentionally allows the DMI implementation to use a simple bus, TileLink, or APB. CV32E40P explicitly provides only the core-side support and calls out the external DM/DTM requirement. Ibex’s demo system shows complete JTAG pin connections. For a first custom CPU, UART-based software diagnostics plus simulation waveforms are a reasonable initial milestone; add the standard debug chain after the architecture and trap behavior stabilize.

### LiteX as an integration/reference platform

[LiteX](https://github.com/enjoy-digital/litex) is a Python framework to connect existing HDL cores and construct FPGA SoCs. It supports multiple pluggable CPUs and includes Wishbone interconnect, CSR/control access, memory, UART, BIOS/firmware integration, and board support. Its license is BSD 2-Clause. LiteX can help with repeatable board bring-up and provide known-good peripheral/reference infrastructure. Integration is easiest when a CPU has an existing LiteX CPU wrapper; adding a custom CPU means writing that wrapper, defining reset/interrupt/debug hooks, and mapping its bus/CSR expectations. It is an SoC builder, not a replacement for designing an original CPU, and adopting it introduces Python tooling and framework conventions.

### Suggested selection by project priority

- **Original CPU authorship and learning:** write the CPU RTL; use an independently implemented simple bus and memory map, reuse licensed UART/GPIO/timer blocks if desired, and keep PicoRV32/Ibex in a separate comparison harness.
- **Fastest small synthesizable RV32 system:** PicoRV32 plus its native/Wishbone port or LiteX integration. Account for archive/maintenance status and describe it as a reused CPU.
- **Verification and debug maturity:** Ibex with its demo-system peripherals, or CV32E40P plus an OBI adapter and PULP debug subsystem. Expect extra integration and dependency work.
- **Very small area experiment:** SERV, with explicit reduced Wishbone-style bridge and firmware performance expectations.
- **Configurable generated FPGA CPU:** VexRiscv where Scala/SpinalHDL and plugin-based configuration are acceptable.
- **Larger/Linux-capable system:** CVA6 or Rocket Chip only if the memory, privilege, coherence, toolchain, and integration scope is intentional.

### Primary sources

- [PicoRV32 official repository and README](https://github.com/YosysHQ/picorv32)
- [Ibex official repository](https://github.com/lowRISC/ibex) and [Ibex demo system](https://github.com/lowRISC/ibex-demo-system)
- [CV32E40P official repository](https://github.com/openhwfoundation/cv32e40p), [manual introduction](https://cv32e40p.readthedocs.io/en/latest/intro.html), and [debug chapter](https://cv32e40p.readthedocs.io/en/latest/debug.html)
- [VexRiscv official repository](https://github.com/SpinalHDL/VexRiscv) and [MIT license](https://github.com/SpinalHDL/VexRiscv/blob/master/LICENSE)
- [SERV official repository](https://github.com/olofk/serv)
- [Rocket Chip official repository](https://github.com/chipsalliance/rocket-chip)
- [CVA6 official repository](https://github.com/openhwfoundation/cva6) and [requirements/license/interface specification](https://github.com/openhwfoundation/cva6/blob/master/docs/02_cva6_requirements/cva6_requirements_specification.rst)
- [LiteX official repository and README](https://github.com/enjoy-digital/litex)
- [RISC-V Debug Specification](https://github.com/riscv/riscv-debug-spec), especially [debug module](https://github.com/riscv/riscv-debug-spec/blob/main/debug_module.adoc) and [introduction](https://github.com/riscv/riscv-debug-spec/blob/main/introduction.adoc)

---

## Verification and debugging plan for a custom RISC-V FPGA CPU

### Recommendation

For a new custom RISC-V core, use an open, Linux-first verification loop: Verilator for fast RTL regressions and lint, cocotb for Python-driven instruction and bus tests, GTKWave or Surfer for waveform inspection, and SymbiYosys with riscv-formal/RVFI for bounded architectural properties. Keep an Icarus Verilog run as a second simulator when the RTL fits its supported subset. Add RISC-V Architectural Compatibility Tests (ACT) once the CPU can boot their self-checking binaries. On the FPGA, use the vendor logic analyzer (AMD ILA or Intel Signal Tap) for cycle-level traces. Add OpenOCD/GDB only when the implemented core includes a compatible RISC-V Debug Module/JTAG path.

Simulation makes failures cheap and repeatable. Formal checks can exhaustively explore selected logic properties. Architectural binaries test integration and software behavior. FPGA probes explain faults that only happen in actual timing and board conditions. None of those layers alone establishes that the processor is bug-free.

### RTL simulation engines

| Tool | Best fit | Advantages | Constraints and practical use |
|---|---|---|---|
| **Verilator** | Fast SystemVerilog RTL simulation, lint, larger randomized regressions | It translates Verilog/SystemVerilog to C++ or SystemC and compiles an executable. It supports tracing and coverage, and is a strong default for a CPU because architectural tests can run many cycles quickly. [Verilator overview](https://verilator.org/guide/latest/overview.html) | It is mostly a two-state simulator. X assignments are mapped according to options rather than behaving like a full four-state simulator, so pair it with a four-state simulator or explicit reset/X-oriented checks when unknown propagation matters. [Language limitations](https://verilator.org/guide/latest/languages.html) cocotb support is available in current releases, but confirm support for the exact version and features in use. |
| **Icarus Verilog (iverilog/vvp)** | Small, portable Verilog/SystemVerilog testbenches and an independent second run | Free, straightforward command line, mature VCD output, and broad availability on Windows/Linux. Its documentation describes ongoing SystemVerilog support and version-selectable language modes. [Icarus docs](https://steveicarus.github.io/iverilog/) [language flags](https://steveicarus.github.io/iverilog/usage/command_line_flags.html) | SystemVerilog support is ongoing rather than full parity with commercial simulators. A project using advanced SV constructs can hit gaps; keep the testbench portable and compile the actual core early. [Icarus installation and platform notes](https://steveicarus.github.io/iverilog/usage/installation.html) |
| **GHDL** | VHDL-only RTL or VHDL testbench verification | Free VHDL analyzer/compiler/simulator; supports analysis, elaboration, execution, and waveform dumping. [GHDL overview](https://ghdl.github.io/ghdl/) [simulation workflow](https://ghdl.github.io/ghdl/quick_start/simulation/index.html) | It is not a SystemVerilog simulator. For a Verilog/SystemVerilog CPU, it is relevant only if the project has VHDL components or a VHDL implementation. cocotb supports GHDL, but its VPI-based interface has limitations for VHDL-specific constructs and nine-valued signals. [cocotb simulator support](https://docs.cocotb.org/en/stable/simulator_support.html) |
| **Commercial simulators** (Questa/ModelSim, Xcelium, VCS, Riviera-PRO, Active-HDL) | Full SystemVerilog/UVM, mixed-language vendor IP, advanced debug/coverage, or a team already licensed | These generally offer broad language support, coverage and advanced debug. Synopsys describes VCS with broad SystemVerilog, coverage, multicore and Verdi integration; Cadence describes Xcelium support for SystemVerilog, VHDL, SystemC, UVM and mixed-signal. [VCS](https://www.synopsys.com/verification/simulation/vcs.html) [Xcelium](https://www.cadence.com/en_US/home/explore/functional-verification.html) | Licensing and installation are meaningful cost and setup overhead for an individual CPU project. Availability may be OS-specific. AMD's current Vivado launch documentation lists supported simulator versions and marks Xcelium/VCS Linux-only and Active-HDL Windows-only for that flow. [Vivado simulator integration matrix](https://docs.amd.com/r/en-US/ug835-vivado-tcl-commands/launch_simulation) |

A productive split is Verilator as the frequent regression engine, Icarus for compatibility and independent semantics, and a vendor simulator only if required by the FPGA build or IP. Verilator's compiled approach makes long instruction streams practical; Icarus' four-state logic can reveal X propagation and provides a useful cross-check. Simulator disagreement is a debugging clue: reduce the failing program and inspect language constructs, initialization, event scheduling, and testbench races.

### Testbenches and architectural checking

**cocotb** lets a Python test drive clocks, reset, memory responses, interrupts, and bus transactions while observing RTL signals. It supports common simulators through VPI/VHPI/FLI, embeds Python in the simulator process, and provides a runner with CI-friendly test reporting. This is a good fit for a small core: use Python to load ELF/hex images, service a simple memory model, compare retirement records, and generate directed plus randomized tests. [cocotb overview](https://docs.cocotb.org/en/stable/) [current simulator support and caveats](https://docs.cocotb.org/en/stable/simulator_support.html)

At the architectural boundary, compare every retired instruction against a trusted reference model. Common choices include Spike, a functional RISC-V ISA simulator, and a small independent reference model for the implemented subset. [Spike project](https://github.com/riscv-software-src/riscv-isa-sim) Capture at least PC, instruction, destination register/write value, memory address/data/mask, and trap metadata at retirement. For a simple single-hart in-order CPU, compare instruction-by-instruction. Align handling of reset, unsupported instructions, memory map, privilege modes, and traps before trusting a mismatch. A reference model only checks what it models and shares assumptions with the test; it cannot find an RTL bug if the checker repeats the same mistake.

Use three complementary stimulus sources:

1. **Directed unit tests** for ALU corner cases, immediate decode, branch conditions, misaligned accesses, load/store lane selection, register x0, reset, stalls, flushes, and traps.
2. **Randomized instruction programs** with constrained legal encodings, varied dependencies, branches, and memory traffic. Keep seeds and save the failing program and retirement trace so every bug is reproducible.
3. **RISC-V ACT tests** for ISA conformance. The riscv-arch-test repository generates self-checking ELFs from a DUT configuration. ACT is useful for normative instruction behavior and interoperability, but its own documentation emphasizes that certification testing is not full verification: it does not cover microarchitectural hazards, timing, or every possible data pattern. [ACT repository](https://github.com/riscv/riscv-arch-test) [certification-vs-verification notes](https://github.com/riscv/riscv-arch-test/blob/act4/docs/ctp/src/intro.adoc)

Run architectural tests in simulation first, then on FPGA once basic board I/O works. They need an execution environment: reset/entry point, RAM or ROM image loading, and a pass/fail reporting path. Start with only the configured ISA subset, such as RV32I or RV32IM, rather than claiming coverage for unimplemented extensions.

### Formal checks: SBY, Yosys, RVFI, and practical limits

**SymbiYosys (sby)** is a front end for Yosys-based formal flows. Its modes include bounded safety checking (BMC), unbounded safety proofs, liveness, and cover-trace generation. [SBY documentation](https://yosyshq.readthedocs.io/projects/sby/en/stable/) A small CPU can benefit from formal checks for local invariants even before end-to-end ISA proof: x0 always reads zero, a writeback only occurs on a valid retirement, a stalled request remains stable, an invalid instruction has defined trap behavior, and a pipeline flush prevents younger instructions from committing.

**riscv-formal** defines the RISC-V Formal Interface (RVFI), an output trace of retired instructions, and supplies processor-independent checks for ISA behavior. Integrating it means wiring retirement data and a wrapper that models memory/peripherals; it is not push-button verification of arbitrary RTL. Its documented focus is RV32I/RV64I and checks may be bounded or unbounded depending on design complexity and proof strength. [riscv-formal project and integration steps](https://github.com/YosysHQ/riscv-formal) [verification procedure](https://github.com/YosysHQ/riscv-formal/blob/main/docs/source/procedure.rst) RVFI details are [here](https://github.com/YosysHQ/riscv-formal/blob/main/docs/source/rvfi.rst).

Formal proof has practical boundaries. Memories, long pipelines, complex bus assumptions, and state-space growth can make runs slow or inconclusive. Bounded checks establish behavior only through the selected depth. The riscv-formal documentation notes that ordinary multiplication/division can be beyond practical model-checking capacity and offers alternative arithmetic operations for proofs of surrounding behavior. [riscv-formal arithmetic limits](https://github.com/YosysHQ/riscv-formal/blob/main/docs/source/rvfi.rst) Use formal on small blocks and architectural retirement first; treat timeout/UNKNOWN as unresolved, not as a pass. Review assumptions carefully, since assumptions restrict what the solver explores.

### Waveforms and failure diagnosis

Dump waveforms only for failing or selected runs. VCD is widely portable and easy to generate, but GTKWave documentation describes it as the slowest and most memory-intensive supported format; FST is optimized for fast sequential and random access. [GTKWave formats](https://gtkwave.github.io/gtkwave/intro/formats.html) Verilator can emit VCD/FST traces when enabled; Icarus uses $dumpfile/$dumpvars and vvp. Keep a short failing trace and a signal grouping/state file for clock/reset, PC, fetch/decode/execute/writeback valid bits, stall/flush, register writeback, memory handshake, and RVFI.

**GTKWave** is a mature post-run viewer for VCD, FST and related formats, available for Windows, Linux, and macOS. [GTKWave documentation](https://gtkwave.github.io/gtkwave/) **Surfer** is a newer viewer for VCD/FST/GHW; its documentation notes that GHW support is less complete than VCD/FST. [Surfer docs](https://docs.surfer-project.org/book/) Either is suitable; use whichever installs cleanly. For long traces, prefer FST. Save a GTKWave .gtkw or Surfer state with the signals and radix settings that make a CPU failure readable.

A useful debug sequence is: identify the first incorrect retirement, locate the earliest pipeline cycle where expected control or data differs, determine whether the error began in fetch/decode/operand selection/forwarding/memory/commit, then reduce the instruction sequence while preserving the mismatch. The retirement trace says what architectural rule failed; the waveform explains how the pipeline produced it.

### FPGA hardware debug

**AMD FPGA:** Vivado Integrated Logic Analyzer (ILA) samples selected internal signals at design speed, triggers on conditions, and captures post-implementation behavior. It can be instantiated in RTL or inserted post-synthesis. [AMD ILA guide](https://docs.amd.com/r/en-US/ug908-vivado-programming-debugging/ILA) It consumes FPGA resources and captures a finite buffer, so probe only signals tied to a hypothesis. Ensure debug probes correspond to the bitstream being programmed. ILA sees actual clock/reset/timing behavior and is the right tool for failures that simulation does not reproduce.

**Intel FPGA:** Quartus Signal Tap captures and displays real-time internal signal behavior in device memory and supports trigger conditions, without requiring extra I/O pins. [Intel Quartus Debug Tools guide](https://www.intel.com/programmable/technical-pdfs/683552.pdf) Signal Tap plays the same role on Intel devices as ILA does on AMD devices. Keep a hardware debug build with useful probe points and a modest capture depth; large probe sets increase resource and timing pressure.

**OpenOCD plus GDB:** This is a software-visible debug path through a JTAG adapter and the RISC-V Debug Module. OpenOCD documents JTAG debug for RV32/RV64 and primarily targets RISC-V Debug Specification 0.13, with legacy 0.11 support. GDB connects to OpenOCD through the remote protocol. [OpenOCD RISC-V support](https://openocd.org/doc/html/Architecture-and-Core-Commands.html) [GDB connection workflow](https://openocd.org/doc/html/GDB-and-OpenOCD.html) A custom CPU without a Debug Module, JTAG DTM, and compatible debug features cannot use this path just because it executes RISC-V instructions. Implementing that infrastructure is a separate design task. For a small FPGA core, UART console plus ILA/Signal Tap is often the faster bring-up path.

### Windows, WSL, and Linux workflow

Open-source simulation and Python tooling are practical on Windows; cocotb aims to support current 64-bit Windows, Linux, and macOS where the simulator itself is supported. [cocotb platform support](https://docs.cocotb.org/en/stable/platform_support.html) Icarus can be installed as a Windows package or built with MSYS2/MinGW/Cygwin. Verilator's current documentation includes Windows setup, and its compiled C++ flow requires a compatible compiler. If development is on Windows, keep simulator, Python, C++ compiler, and waveform viewer on one side of the Windows/WSL boundary to avoid PATH and filesystem confusion.

For the open-source Yosys/SBY/riscv-formal stack, Linux or WSL2 is generally the smoother path because the tools and scripts are Linux-oriented; riscv-formal's quickstart calls for Yosys, SBY, Boolector, and Python dependencies. [riscv-formal prerequisites](https://github.com/YosysHQ/riscv-formal/blob/main/docs/source/quickstart.rst) WSL2 can run Linux command-line tools and GUI apps; GUI support requires WSL2 and the appropriate Windows/vGPU setup. [Microsoft WSL FAQ](https://learn.microsoft.com/en-us/windows/wsl/faq) [WSLg setup](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps)

For actual FPGA programming and capture, prefer the native Windows or supported native Linux vendor tool installation. WSL USB access is not built in; Microsoft documents USB/IP via usbipd-win as the route to attach a device to WSL2, and the device becomes unavailable to Windows while attached. [WSL USB connection guide](https://learn.microsoft.com/en-us/windows/wsl/connect-usb) Vendor programming/debug software has its own supported OS and cable drivers, so WSL access is board- and tool-specific. AMD's Vivado documentation and commercial simulator matrices identify OS support explicitly. [Vivado simulator OS matrix](https://docs.amd.com/r/en-US/ug835-vivado-tcl-commands/launch_simulation)

A sensible Windows setup is: use WSL2 Ubuntu for Verilator/Icarus, Python/cocotb, Yosys/SBY, Spike/ACT, and source-controlled scripts; use Windows GTKWave/Surfer or WSLg for viewing; use native Vivado/Quartus for synthesis, bitstream creation, JTAG programming, ILA/Signal Tap, and board cable drivers. Keep the Git checkout inside the WSL Linux filesystem for repeated Linux builds when possible, since cross-boundary file access has different performance and path behavior. Windows and WSL can access each other's files, but mixed-tool execution has different environment and device behavior. [Microsoft WSL FAQ](https://learn.microsoft.com/en-us/windows/wsl/faq)

### Suggested rollout

1. Add deterministic reset, memory model, and a retirement trace. Run a minimal smoke program under Icarus and Verilator.
2. Add cocotb directed tests for ALU, decode, memory lanes, branches, stalls/flushes, and reset. Add seeded randomized programs and keep failure artifacts.
3. Add instruction-by-instruction reference comparison using Spike or a subset reference model.
4. Add RVFI and run riscv-formal checks for supported base ISA instructions; add block-level SBY properties for control invariants.
5. Run configured ACT ELFs in simulation. Once board bring-up works, run the same ELFs on hardware.
6. On FPGA failures, capture focused ILA/Signal Tap signals; add OpenOCD/GDB if a Debug Module is part of the intended core architecture.

This gives fast feedback from the first RTL blocks through full software execution, while matching effort to the evidence each stage provides.


---

## FPGA board choices for building a RISC-V core

**Research date: 2026-10-23.** Prices below are live listings or dated references, not promises of availability. Board pricing excludes tax, shipping, add-on modules, and any regional differences. Chip vendor resource counts use each vendor's own terminology; LUTs, logic cells, and logic elements are not directly comparable.

### Recommendation

For learning CPU design in HDL with the least proprietary-tool friction, choose an **iCEBreaker with iCE40UP5K**. Its 5,280 four-input LUTs and roughly 1.1 Mbit combined on-chip RAM give room for a compact teaching core and simple peripherals, and the board explicitly targets the Yosys/nextpnr/IceStorm flow. At the current $79.95 listing it is an accessible standalone option, though the seller showed only two units when checked. Its on-chip memory remains small for a software-rich SoC; add the optional HyperRAM PMOD or select another board if external RAM matters.

For a more capable soft-core system with external memory and still excellent open-source flow support, choose **ULX3S ECP5**, especially the 85F if budget permits. It has 32 MB SDRAM and a substantially roomier fabric, but current Crowd Supply listing is $275 and marked in stock. The 12F listing is $155 and says pre-order; check shipment status before buying.

Choose **Arty A7-100T** when conventional vendor tools, Ethernet, 256 MB DDR3L, and broad expansion matter more than price; current Digilent price is $322. The Arty A7-35T has been retired, and Basys 3 remains a fine teaching board but has no external main memory listed. **DE10-Lite** provides a different vendor ecosystem and external SDRAM at a historically low academic price, but current official pricing was not reliably exposed in the pages reviewed. **Tang Nano 20K** gives ample advertised LUT and SDRAM resources for a low-cost SoC experiment, but its vendor tool license workflow and younger open-source support make it a less frictionless default.

### Board comparison

| Board | FPGA and advertised fabric | Memory on board | Useful I/O / debug | Tool flow and OS notes | Price evidence checked |
|---|---|---|---|---|---|
| **iCEBreaker** | Lattice iCE40UP5K: 5,280 LUTs, 120 kbit EBR, 1,024 kbit SPRAM, 1 PLL, 8 DSP blocks. The UP5K has 39 user I/O in QFN, but board routing determines what is actually available. | No external RAM on base board. It has SPI configuration; optional HyperRAM PMOD is offered. | Open-source educational board; expansion via PMODs and broken-out GPIO. | Yosys, nextpnr, IceStorm, Icarus Verilog and Amaranth are named by the board maker. A free open-source path works on common Linux/Windows/macOS setups through community packages, though exact package support varies. | **$79.95 USD**, 1BitSquared product listing checked 2026-10-23; only two units shown. [Product listing](https://1bitsquared.com/products/icebreaker). |
| **ULX3S** | Lattice ECP5 LFE5U-12F or -85F. Seller describes 12k / 84k LUT variants (vendor ECP5 counts are architecture-specific). ECP5 includes embedded block RAM and DSP; exact totals vary by part. | 32 MB SDRAM, plus configuration flash. | Board includes USB programming, serial/debug facilities and broad connector set; check the board's hardware documentation for exact revision details. | Strong Yosys/nextpnr support via Project Trellis; nextpnr lists ECP5 as supported. Open-source flow available across Linux, Windows and macOS through native or packaged builds. | **$155** for 12F (pre-order; listed ship date Dec 15, 2026); **$275** for 85F (in stock), plus shipping. Crowd Supply checked 2026-10-23. [Current listing](https://www.crowdsupply.com/radiona/ulx3s). |
| **Arty A7-35T / 100T** | AMD Artix-7 XC7A35T: 33,280 logic cells, 1,800 Kbit block RAM, 90 DSP. XC7A100T: 101,440 logic cells, 4,860 Kbit memory, 240 DSP. These are vendor logic-cell counts, not a direct LUT comparison. | Current Arty A7 listing specifies 256 MB DDR3L x16, 16 MB QSPI. | 10/100 Ethernet, USB-UART, USB-JTAG, Pmods, Arduino/chipKIT header. | Digilent documents free Vivado support for these parts using the older WebPACK naming; check exact device coverage under the current Vivado BASIC licensing tier. AMD publishes supported Windows and Linux releases; not macOS. Yosys/nextpnr 7-series support is experimental, so use Vivado for a dependable flow. | **35T retired** per Digilent. **100T $322** on Digilent listing checked 2026-10-23. [Product and specs](https://digilent.com/shop/arty-a7-100t-artix-7-fpga-development-board/). |
| **Basys 3** | AMD Artix-7 XC7A35T: 33,280 logic cells, 1,800 Kbit block RAM, five clock-management tiles, 90 DSP. | No external DDR/SDRAM listed; on-chip block RAM and serial flash. | USB-JTAG, USB-UART, VGA, USB HID host, switches, buttons, LEDs, seven-segment display, Pmods. Excellent self-contained teaching I/O. | Digilent documents free Vivado support using older WebPACK naming; verify device coverage in the current BASIC tier. Use Vivado for dependable implementation; open-source 7-series support remains experimental. | The current official source reviewed confirmed the SKU and specs but did not expose a dependable current price. Check Digilent/resellers at purchase time. [Digilent product page](https://digilent.com/shop/basys-3-amd-artix-7-fpga-trainer-board-recommended-for-introductory-users/). |
| **DE10-Lite** | Intel/Altera MAX 10 10M50DAF484C7G: about 50K logic elements. MAX 10 provides embedded memory and integrated configuration; use the device datasheet for exact density breakdown. | Terasic lists 64 MB SDRAM (16-bit), plus on-chip flash/configuration. | On-board USB-Blaster, VGA, Arduino UNO R3 header, GPIO, switches/LEDs, accelerometer. USB-Blaster gives JTAG access; board-level UART is not a headline built-in feature, so plan a USB-UART adapter or GPIO UART. | Quartus Prime Lite is free and supports MAX 10. Altera publishes Windows and Linux support for Lite. The Yosys ecosystem does not offer the same stable, complete flow for this MAX 10 target as it does for iCE40/ECP5. | Terasic's current product page describes it as cost-effective but no numeric price was reliably retrievable. Intel's **March 2022** professor slide lists $64, a dated historical reference only; do not treat that as current. [Terasic product page](https://www.terasic.com.tw/cgi-bin/page/archive.pl?CategoryNo=234&Language=English&No=1021). |
| **Tang Nano 20K** | Gowin GW2AR-LV18QN88C8/I7: 20,736 LUT4, 15,552 FF, 828 Kbit block SRAM, 48 multipliers, 2 PLL. | 64 Mbit (8 MB) 32-bit SDR SDRAM; 64 Mbit configuration flash. | BL616 onboard controller provides FPGA JTAG, USB-to-UART, USB-SPI and clock-chip management. 27 MHz crystal, additional MS5351 clock outputs, HDMI, LCD, TF card, audio. | Gowin EDA is available for Windows and Linux; official RISC-V package page says registration and applying for a design license are required for that flow. nextpnr lists Gowin support through Apicula, but this is a developing open-source flow rather than the long-established iCE40/ECP5 experience. | Sipeed pages link to purchase but did not show a trustworthy live USD price in the sources reviewed. Check their current store/resellers. [Board spec](https://wiki.sipeed.com/hardware/en/tang/tang-nano-20k/nano-20k.html), [tool/license instructions](https://www.gowinsemi.com/en/support/ip_detail/23/). |

### What “enough FPGA” means for a RISC-V project

A very small teaching core can be built from a program counter, register file, ALU, decoder/control, and a small memory interface. That is a modest design relative to all of these boards, but resource fit depends strongly on implementation choices: single-cycle versus multicycle, register-file mapping, pipeline depth, ISA extensions, debug support, and whether memories infer FPGA block RAM. The table does not claim a particular core's LUT use or maximum clock rate.

The next step up is a useful soft-core SoC: core plus instruction/data memory, timer, UART, GPIO, interrupt logic, and a practical software image. Here on-chip RAM capacity and external memory access become more decisive than raw LUT count. The iCEBreaker can teach the CPU and peripherals well but constrains software memory; ULX3S, Arty A7, DE10-Lite and Tang Nano 20K add external RAM. If you want Linux-class experimentation or substantial firmware, choose a board with external RAM and enough fabric, and account for the complexity of its memory controller and boot path.

As a rough project-fit guide, not an implementation guarantee:

- **Teaching core, LEDs/UART, small BRAM program:** iCEBreaker, Basys 3, Tang Nano 20K.
- **Core plus monitor/firmware and external-memory experiments:** ULX3S, Arty A7, DE10-Lite, Tang Nano 20K.
- **More room for pipelining, caches, debug, or multiple peripherals:** ULX3S-85F or Arty A7-100T. The 100T is notably expensive at the current listing.

### Practical buying decision

1. **Best toolchain-first learning pick:** iCEBreaker. It makes the open-source HDL flow part of the lesson and has enough logic to move beyond a toy CPU, while its RAM is the main ceiling.
2. **Best open-source headroom:** ULX3S ECP5. Strong fabric and external SDRAM are attractive for a fuller system; the 85F costs substantially more, and current shipment/stock details matter.
3. **Best conventional vendor environment:** Arty A7-100T. Choose this if Vivado, Ethernet, DDR3L, and expansion are important and $322 is acceptable. Consider a used Arty A7-35T only if the price is compelling and condition is clear; Digilent marks it retired.
4. **Best conventional teaching board:** Basys 3. Its built-in switches, displays, VGA, USB HID and Pmods make hardware exercises easy; plan to keep the system small because no external main RAM is specified.
5. **Choose DE10-Lite for MAX 10 / Quartus learning** or because a course specifically uses it. A teaching core is straightforward, with external SDRAM available, but current acquisition price and host OS/tool setup should be checked before ordering.
6. **Choose Tang Nano 20K for compactness and resources per board** if comfortable with Gowin EDA license registration or the state of Apicula. Its 8 MB SDRAM is useful for a compact SoC, and the onboard BL616 simplifies USB serial/JTAG.

### Sources

Primary and board-maker sources consulted (accessed 2026-10-23):

- Lattice [iCE40 UltraPlus family table and datasheet](https://www.latticesemi.com/Products/FPGAandCPLD/iCE40UltraPlus?ActiveTab=Key+Documents).
- 1BitSquared [iCEBreaker product, price and supported design flow](https://1bitsquared.com/products/icebreaker).
- Radiona/Crowd Supply [ULX3S variants, price, inventory and shipment status](https://www.crowdsupply.com/radiona/ulx3s); [project resources](https://ulx3s.github.io/).
- Digilent [Arty A7 product specifications, price and retirement status](https://digilent.com/shop/arty-a7-100t-artix-7-fpga-development-board/); [Basys 3 specifications](https://digilent.com/shop/basys-3-amd-artix-7-fpga-trainer-board-recommended-for-introductory-users/).
- AMD [Vivado OS support](https://www.amd.com/en/support/adaptive-socs-and-fpgas/installer-info-general.html) and [WebPACK device coverage](https://docs.amd.com/api/khub/documents/NgPmyK_NDy4EEh~88JFUfQ/content).
- Terasic [DE10-Lite product page](https://www.terasic.com.tw/cgi-bin/page/archive.pl?CategoryNo=234&Language=English&No=1021); Intel [March 2022 professor resource slide with historical board prices](https://cdrdv2-public.intel.com/685254/FPGA-professor-resources-march-2022.pdf).
- Altera [Quartus Prime editions](https://www.altera.com/products/software-tools/quartus-prime) and [OS support information](https://www.altera.com/design/guidance/software/os-support?wapkw=FPGA).
- Sipeed [Tang Nano 20K specifications](https://wiki.sipeed.com/hardware/en/tang/tang-nano-20k/nano-20k.html); Gowin [RISC-V toolchain and license instructions](https://www.gowinsemi.com/en/support/ip_detail/23/).
- YosysHQ [nextpnr supported FPGA architectures](https://github.com/YosysHQ/nextpnr).

---

## Implementation roadmap

| Milestone | Deliverable | Evidence to collect |
|---|---|---|
| 0. Freeze scope | ISA/EEI specification, board shortlist, memory map, reset/trap policy | Exact spec versions, selected extensions, tool/license/device support |
| 1. Establish tools | Reproducible simulation and firmware build | Tiny RTL smoke test and disassembled RV32I program |
| 2. Build datapath | Register file, immediate decoder, ALU, branch unit | Tests for x0, signedness, shifts, overflow wraparound, branch decisions |
| 3. Execute instructions | Multicycle control, fetch, load/store handshake | Directed assembly tests and retirement traces; injected memory stalls |
| 4. Complete architectural behavior | Declared RV32I behavior and chosen EEI/trap handling | Illegal instructions, alignment, access faults, ECALL/EBREAK, FENCE behavior |
| 5. Verify the core | Differential checks and applicable architectural tests | Reproducible test results, random seeds, failure waveforms; documented coverage gaps |
| 6. Build minimal SoC | Block RAM/ROM, UART, GPIO, reset and clock wrapper | Same firmware runs in simulation; RAM byte enables and read latency checked |
| 7. Deploy to FPGA | Constraints, implementation scripts, programming steps | Timing closure at declared clock, utilization, hardware UART output and LED test |
| 8. Extend deliberately | M, C, machine CSRs/interrupts, pipeline, or custom operations | Workload motivation plus regression results and measured area/timing changes |

The extension sequence is a menu, not a dependency chain: machine CSRs and interrupts may matter before compressed instructions. A five-stage pipeline is a later design option; it introduces forwarding, stalls, flushes, and precise exception requirements. Linux is a separate scope increase involving privilege/platform/software expectations and memory capacity.

## Decisions still open

- Existing FPGA board, if any; otherwise board budget and purchasing region.
- HDL experience and preference for native Windows versus WSL/Linux tooling.
- Primary aim: learn CPU design, maximize performance, minimize area, or explore custom instructions.
- Initial firmware workload and memory capacity target.
- Desired clock target after an initial synthesis experiment; no MHz or LUT estimate is established yet.
- Bus choice, reset PC, RAM/ROM map, trap policy, and initial external debug requirements.

## Research maintenance

Record tool versions and selected repository commits in a manifest. Keep copied or generated IP licenses alongside the relevant modules. Save experiment outcomes with the FPGA part number, constraints, configuration, software workload, and command used. LUT counts across vendors are not directly comparable, and a simulation pass does not establish FPGA timing closure.


## Purchase shortlist: FPGA boards under $500

Checked October 23, 2026. Prices are USD and exclude tax and shipping unless specified. Listings and stock can change. This shortlist updates the buying guidance above; manufacturer prices and distributor prices can differ.

Recommendation: Arty A7-100T new for the overall custom CPU/SoC development path; Nexys 4 DDR used for value; ULX3S-85F for an open-source implementation flow. These are engineering recommendations, not measured resource-fit guarantees for our core.

| Board | Price and condition observed | Fit for this project | Tradeoff |
|---|---|---|---|
| [Arty A7-100T at TEquipment](https://www.tequipment.net/Digilent/Arty-A7-100T/FPGA/) | $322 new; listed in stock | Artix-7 100T, 256 MB DDR3L, Ethernet, USB-UART/JTAG. Best overall starting choice for a custom CPU with SoC growth room. | DDR requires controller integration. [Manufacturer specifications](https://digilent.com/shop/arty-a7-100t-artix-7-fpga-development-board/). |
| [Nexys 4 DDR, used listing](https://www.ebay.com/itm/287656779274) | $199.99 used, or best offer; shipping varies | Artix-7 100T, 128 MiB DDR2; best used value found. Functionally equivalent to Nexys A7-100T. | Seller accepts no returns. Confirm JTAG programming and RAM operation before purchase. [Official board manual](https://digilent.com/reference/_media/reference/programmable-logic/nexys-a7/nexys-a7_rm.pdf). |
| [Nexys A7-100T](https://digilent.com/shop/nexys-a7-amd-artix-7-fpga-trainer-board-recommended-for-ece-curriculum/) | $349 manufacturer price; [DigiKey listing](https://www.digikey.com/en/products/detail/digilent-inc/410-292/5117190) showed $429.97 and stock | Artix-7 100T, 128 MiB DDR2, VGA, switches, displays, Ethernet and onboard programming. Strong self-contained lab board. | More onboard features than needed for first CPU bring-up; compare distributor totals. |
| [ULX3S-85F](https://www.crowdsupply.com/radiona/ulx3s) | $275 new plus $8 US shipping; latest opened page showed in stock | ECP5 with about 84K LUTs, 32 MB SDRAM, microSD, USB serial/programming. Best open-source-tool option. | Stock differed between search/page snapshots; verify at checkout. Less external RAM than Arty/Nexys. |
| [Basys 3](https://digilent.com/shop/basys-3-amd-artix-7-fpga-trainer-board-recommended-for-introductory-users/) | $165 new | Artix-7 35T, switches, LEDs, displays and onboard programming. Economical learning board. | No external main RAM; less room for large software and SoC experiments. |

### Additional marketplace options

- [Nexys 4 DDR, open box](https://www.ebay.com/itm/377093913425): $209; five shown available. Ships from Taiwan; displayed international shipping was about $60, dependent on destination. Seller accepts no returns.
- [Arty A7-100T, used](https://www.ebay.com/itm/327368809204): $279 plus shipping. At $43 below the observed new price, new is preferable unless a lower offer is accepted. Seller accepts no returns.

Use the exact FPGA part, board revision, power supply requirements, cable/programmer inclusion, documentation, and tool device support when comparing offers. For used boards, seek evidence of successful programming and memory testing. The listed boards provide a CPU development platform; full RVA23 implementation fit requires a separate resource estimate for the selected microarchitecture. Start in block RAM before integrating external memory.

## Updated focus: LLM accelerator board selection

October 23, 2026: the earlier Arty/Nexys/ULX3S recommendations above concern the original RISC-V CPU project. The current complete Qwen text/vision shared-engine design has different memory and transport requirements. See [FPGA resource and board analysis](fpga-resource-and-board-analysis.md) alongside [plan.md](plan.md) and [memory-plan.md](memory-plan.md).

The initial eight-lane integrated development budget is **40–90k physical LUT6, 25–80 DSPs and 70–170 RAMB36 equivalents**, including one DDR and one PCIe DMA subsystem. These are assumptions bounded by published implementation examples, not measurements of our RTL. The preferred development board is a documented **RK-XCKU5P-F V1.2**: 216,960 LUT6, 2 GiB DDR4, onboard JTAG/UART and documented PCIe Gen3 x4. An observed candidate is about **$291 including displayed shipping**, subject to matching the exact PCB revision. A used generic XC7K325T listing at about **$69 including displayed shipping** is the cheapest large-fabric alternative, with memory, programming and constraints still unverified. Prices exclude tax and vary by destination.

The companion analysis links listings, primary device/tool documentation and existing LiteX board targets. It also identifies the RK target's default 1-GiB address mapping and the seller-title x8 discrepancy. None of these small-DDR boards holds the complete 54.71-GB BF16 model; full-graph development requires streamed weights and explicit host-link performance accounting. Preserve the free simulation-first workflow and establish actual synthesis/resource reports before treating a board fit as proven.

### Plan completeness audit

The [plan gap audit](plan-gap-audit.md) now specifies 15 previously incomplete areas, including BF16 intermediate casts, FMA feedback scheduling, a concrete packed layout/DDR allocation, versioned command and DMA contracts, cancellation/context invalidation, processor/video metadata, two generation EOS IDs, bounded development workloads, independent numerical/fault tests, physical integration and native simulation runtime. New planning checks verify source identity and allocation/traffic arithmetic; they do not constitute an RTL or hardware result. The updated main plan and memory analysis incorporate the consequential decisions.
