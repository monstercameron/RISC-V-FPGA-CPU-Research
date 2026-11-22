# RV64GC execution environment and Linux: requirements, staged plan, golden models, first milestone

Research note for the council. Written 2026-11-22, `date` 04:09 EST at start, 04:18 at the start of writing.
Repository at `4d13324` (architecture 0.17.4). Read-only: no tracked file changed. Nothing was downloaded
or built, and no prototype was run.

Labels: **Fact** has a URL (official sources, fetched today) or a repository path. **Judgement** is my
recommendation or estimate. **Memory** is something I believe but did not fetch today; verify it before
it goes into a contract.

Builds on `build/research/isa-roadmap.md` (the "roadmap") and `build/research/js-engines.md`, and does
not repeat them. `build/research/isa-verification.md` does not exist; the roadmap's section 3 covers the
official suites.

---

## 0. Summary

- **What Linux actually needs** (Fact, section 1):
  - **ISA:** rv64ima + Zicsr + Zifencei. The kernel's `-march` always starts with `rv64ima`.
  - **Modes and MMU:** M/S/U with Sv39. A, D and access are handled as page faults (Svade is
    enough). SFENCE.VMA and WFI.
  - **Platform:** a 64-bit timer (CLINT/ACLINT MTIMER), a console, a device tree, and OpenSBI in M-mode.
  - **Not needed to boot:** C and F/D. C (`CONFIG_RISCV_ISA_C`) and the FPU are kernel options.
    Misaligned access, the `time` CSR and even AMOs (on an LR/SC-only hart) can be emulated by OpenSBI
    or the kernel.
  - **Needed for distro binaries:** "RV64GC" (C and F/D) is needed to run stock distribution
    binaries, Node and V8. It is not needed to boot to a busybox shell.
- **Minimal platform** (Judgement, section 1.5), "lab-virt":
  - Spike's memory map, so that one DTB runs unchanged on Spike, rv_iss and the RTL SoC.
  - Devices: one hart, DRAM at 0x8000_0000 (64 MiB), a boot ROM at 0x1000, a SiFive-layout CLINT at
    0x0200_0000, an ns16550a at 0x1000_0000, an optional 1-source PLIC at 0x0c00_0000, and a test
    finisher for the end of a run.
  - Software: OpenSBI `fw_jump`, then Linux with a busybox initramfs.
- **Order** (Judgement, section 3):
  - Golden model first: rv_iss boots Linux before any RTL work starts.
  - Then the roadmap's M-mode steps 7-11, then A, then S/U, then Sv39. The multicycle core goes
    first, because Verilator runs it at about 6.3M instructions/s, so a full RTL boot takes minutes.
  - Then the SoC devices, then the pipelined core, then the out-of-order core, then C.
  - Each of these is its own MINOR version, behind a define that is off by default.
  - **This departs from the roadmap**, which put the S track after RVA23U64 closure and kept A, C and
    Sv39 off the multicycle core.
- **Golden models** (Judgement, section 4):
  - rv_iss.c becomes the system-mode workhorse: boot, checkpoints and RTL lockstep.
  - **Spike** (BSD-3) is the privileged authority. Its commit logs are compared with rv_iss.
  - **Sail** (BSD-2) arbitrates disputes and supplies the ACT signatures.
  - reference.py stays the user-mode authority and gains only the M-mode trap subset.
- **First milestone M1** (Judgement, section 5):
  - rv_iss `--sys` boots OpenSBI, Linux and busybox to a shell.
  - It agrees with Spike over the first part of the boot, passes riscv-tests rv64mi/si/ua/uc and the
    `v` env, and writes full-system checkpoints.
  - About 2-3 weeks of agent work. No RTL changes, so no version bump.

---

## 1. Exactly what Linux needs

### 1.1 ISA (Fact)

| Item | Fact | Source |
|---|---|---|
| Kernel base ISA | `riscv-march-$(CONFIG_ARCH_RV64I) := rv64ima`; `fd` appended when `CONFIG_FPU`, `c` when `CONFIG_RISCV_ISA_C`, `v` when `CONFIG_RISCV_ISA_V`, then `_zicsr_zifencei` with newer toolchains | https://raw.githubusercontent.com/torvalds/linux/master/arch/riscv/Makefile |
| A is not optional for the kernel | The base string always contains `a` | same |
| C is optional | `RISCV_ISA_C` default y; help: the kernel "won't run on systems without compressed instruction support" when enabled, so a kernel built with it off runs without C | https://raw.githubusercontent.com/torvalds/linux/master/arch/riscv/Kconfig |
| F/D optional | `FPU` default y, "when an FPU is detected at boot"; userspace flags default `-march=rv64g -mabi=lp64d` | same |
| Userspace ABI baseline | hwprobe `BASE_BEHAVIOR_IMA`: "Support for rv32ima or rv64ima, as defined by version 2.2 of the user ISA and version 1.10 of the privileged ISA"; `fence.i` is not usable directly from user mode (use the flush-icache syscall) | https://docs.kernel.org/arch/riscv/hwprobe.html |
| Detected-at-boot, optional | Zicbom (selects `RISCV_DMA_NONCOHERENT`; needed only for non-coherent DMA), Zicboz, Svpbmt, Svnapot, Zbb, Zawrs, V | Kconfig, above |
| Misaligned | `RISCV_PROBE_UNALIGNED_ACCESS` (default): "If unaligned accesses trap, the kernel emulates them"; uabi: "Misaligned scalar accesses are supported in userspace, but they may perform poorly" | Kconfig; https://docs.kernel.org/arch/riscv/uabi.html |
| OpenSBI base | "At least rv32ima_zicsr or rv64ima_zicsr required on all HARTs"; atomics may be limited to Zalrsc (`rv64im_zalrsc_zicsr`); the source tree has `sbi_illegal_atomic.c` (AMO emulation) | https://raw.githubusercontent.com/riscv-software-src/opensbi/master/docs/platform_requirements.md ; https://github.com/riscv-software-src/opensbi/tree/master/lib/sbi |
| `time` CSR | OpenSBI: "TIME CSR is optional"; without it "a 64-bit MMIO counter is required to track time and emulate TIME CSR"; `sbi_emulate_csr_read` emulates `CSR_TIME`, `CSR_CYCLE` and `CSR_INSTRET` for S and U (licence `BSD-2-Clause`) | platform_requirements.md; https://raw.githubusercontent.com/riscv-software-src/opensbi/master/lib/sbi/sbi_emulate_csr.c |

Judgement:
- **The minimum ISA for a busybox boot is rv64ima_zicsr_zifencei.** It must have a working `time`
  source; native Zicntr is cheap and avoids a trap on every `rdtime`.
- **"RV64GC" means IMAFD + C + Zicsr + Zifencei.** It matters for stock distro userspace (Debian and
  Fedora are rv64gc, and V8 needs F/D: js-engines.md 2.3). It does not matter for the boot itself.
- **Our cores have none of A, C, Zicsr (beyond fcsr) or privilege.** F/D exists only on the
  out-of-order core (architecture.md section 1).
- **Zicbom is irrelevant:** our SoC has no DMA.

### 1.2 Privilege (Fact unless marked)

- **Modes:** M, S and U.
  - OpenSBI: "At least one HART should have S-mode support". "The MTVEC CSR on all HARTs must support
    direct mode" (platform_requirements.md).
  - PMP is optional. Without it OpenSBI "cannot protect M-mode firmware" (same).
- **Kernel entry:** `a0` = hart ID, `a1` = DTB address, and "$satp = 0: the MMU, if present, must be
  disabled". The image must be "2MB aligned for rv64". Ordered boot uses SBI HSM; spinwait is the
  legacy path (https://docs.kernel.org/arch/riscv/boot.html).
- **SBI calling convention:** `a7` EID, `a6` FID, `a0`/`a1` error/value. "All functions in the base
  extension must be supported by all SBI implementations"
  (https://docs.riscv.org/reference/sbi/v3.0/ext-base.html; binary encoding:
  https://github.com/riscv-non-isa/riscv-sbi-doc/blob/master/src/binary-encoding.adoc).
  - OpenSBI provides Base, Legacy, TIME, IPI, RFENCE, HSM, SRST, DBCN, PMU and FWFT, among others
    (the `sbi_ecall_*.c` list, Fact).
- **What the hardware must have** (Judgement, from the privileged spec v1.13 and the OpenSBI and
  Linux sources above):
  - M-mode CSRs: mstatus (MIE, MPIE, MPP, SIE, SPIE, SPP, MPRV, SUM, MXR, TVM, TW, TSR, FS, SD, UXL
    and SXL read-only 2), misa, medeleg, mideleg, mie, mip, mtvec, mepc, mcause, mtval, mscratch,
    mhartid, mcounteren, menvcfg and mcountinhibit.
  - S-mode CSRs: sstatus, sie, sip, stvec, sepc, scause, stval, sscratch, satp, scounteren and senvcfg.
  - Counters: cycle, time and instret.
  - Instructions: mret, sret, wfi and sfence.vma.
  - Traps: the synchronous exception priority order. Delegation through medeleg/mideleg. Interrupts:
    MTI, MSI, MEI and their S-level forms (STIP is written by OpenSBI's timer path when Sstc is
    absent).
  - OpenSBI probes optional CSRs with a trap-catching read. Absent optional CSRs (PMP, hpm, menvcfg on
    old specs) must raise illegal instruction cleanly. Memory: verify against `sbi_hart.c` before the
    contract is written.
- **RVA23S64 is a different, larger target** (roadmap section 1.4: Sha/H, Svpbmt, Sstc, Sscofpmf and
  others are mandatory there). Name this work an "S-mode + Sv39 Linux experiment", as
  architecture.md section 6 already warns.

### 1.3 MMU (Fact)

From https://github.com/riscv/riscv-isa-manual/blob/main/src/priv/supervisor.adoc:

- **Sv39:** a 39-bit VA, 4 KiB pages, three levels, and 2 MiB/1 GiB superpages; `satp.MODE` = 8.
  Bits 63-39 must equal bit 38, or the access page-faults.
- **A/D bits:**
  - Under Svade, "a page-fault exception is raised" when A is clear, or D is clear on a write;
    software sets the bits.
  - Without Svade, hardware sets them atomically.
  - "All harts must use the same PTE-update scheme."
- **SFENCE.VMA** orders this hart's earlier stores before its later implicit page-table reads, and
  invalidates matching translations. `rs1` and `rs2` give address and ASID scope.
- **Page faults:** causes 12, 13 and 15.
- **Mode choice:** Linux probes Sv57, then Sv48, then Sv39 by writing satp and reading it back. "if
  (hw_satp != identity_satp)" means it falls back (`set_satp_mode`,
  https://raw.githubusercontent.com/torvalds/linux/master/arch/riscv/mm/init.c). Sv39 alone is enough;
  user space then has 256 GB (https://docs.kernel.org/arch/riscv/vm-layout.html).
- **Not needed for a boot:** Sv48, Svpbmt and Svnapot.

Judgement:
- **Choose Sv39 + Svade (no hardware A/D update).** The page walker then never writes memory.
  - Linux handles A/D faults.
  - Spike and Sail both implement Svade and Svadu (their READMEs, Fact), so the reference can be
    configured to match.
  - On the out-of-order core this removes speculative PTE writes entirely.
- **ASIDs: implement 0 bits at first** (ASIDLEN = 0 is legal). Every SFENCE.VMA then flushes
  everything.

### 1.4 Platform (Fact)

- **ACLINT** (https://github.com/riscv/riscv-aclint/blob/main/riscv-aclint.adoc):
  - MTIME is 64-bit and reset to 0. MTIMECMP is per hart, and "The machine-level timer interrupt of a
    HART is pending whenever MTIME is greater than or equal to" it.
  - MSWI has one 32-bit MSIP per hart.
  - A SiFive CLINT is an MSWI at 0x0000-0x3FFF followed by an MTIMER at 0x4000-0xBFFF.
- **Spike's platform** (https://raw.githubusercontent.com/riscv-software-src/riscv-isa-sim/master/riscv/platform.h):

| Item | Value |
|---|---|
| Reset vector | `DEFAULT_RSTVEC 0x00001000` |
| CLINT | `CLINT_BASE 0x02000000`, size 0xc000 |
| PLIC | `PLIC_BASE 0x0c000000`, 31 devices, 4 priority bits |
| UART | `NS16550_BASE 0x10000000`, reg-shift 0, 1-byte I/O, IRQ 1 |
| DRAM | `DRAM_BASE 0x80000000` |
| Default ISA | `DEFAULT_ISA "rv64imafdc_zicntr_zihpm"` |
| Boot arguments | `DEFAULT_KERNEL_BOOTARGS "console=ttyS0 earlycon"` |

  - Its timer: `INSNS_PER_RTC_TICK = 100; // 10 MHz clock for 1 BIPS core`
    (https://raw.githubusercontent.com/riscv-software-src/riscv-isa-sim/master/riscv/sim.h).
  - Licence BSD-3-Clause, "Copyright (c) 2010-2017, The Regents of the University of California".
- **QEMU virt** (https://www.qemu.org/docs/master/system/riscv/virt.html):
  - CLINT (ACLINT with `aclint=on`), PLIC or AIA, 1-2 NS16550 UARTs, a Goldfish RTC, a SiFive Test
    device, 8 virtio-mmio devices, PCIe, CFI flash and fw_cfg.
  - The DTB is generated by QEMU. A custom one needs a CLINT node `"riscv,clint0"` for OpenSBI.
- **OpenSBI generic platform** (https://raw.githubusercontent.com/riscv-software-src/opensbi/master/docs/platform/generic.md):
  - Everything is driven by the FDT. "Every platform needs a timer device node". Multi-hart platforms
    need an IPI node; `stdout-path` selects the console.
  - Firmware kinds (https://raw.githubusercontent.com/riscv-software-src/opensbi/master/docs/firmware/fw.md):
    `fw_jump` (next stage at a fixed address), `fw_payload` (kernel embedded) and `fw_dynamic`. The
    hand-off is `a0` = hart ID and `a1` = DTB, 8-byte aligned.
- **DT CPU binding**
  (https://raw.githubusercontent.com/torvalds/linux/master/Documentation/devicetree/bindings/riscv/cpus.yaml):
  - Required: an `interrupt-controller` child (`riscv,cpu-intc`).
  - Either `riscv,isa` or the pair `riscv,isa-base` + `riscv,isa-extensions`.
  - `mmu-type` is one of `riscv,sv32/39/48/57/none`.
- **Console without a kernel UART driver:** `HVC_RISCV_SBI` (an SBI console) exists but "depends on
  RISCV_SBI && NONPORTABLE"
  (https://raw.githubusercontent.com/torvalds/linux/master/drivers/tty/hvc/Kconfig). The LiteX
  VexRiscv log uses `hvc0`.

### 1.5 The minimal "boots to a busybox shell" platform (Judgement)

**lab-virt, single hart.** It deliberately uses Spike's addresses and timer rule.

| Block | Choice | Why |
|---|---|---|
| Hart | rv64ima_zicsr_zifencei + Zicntr, M/S/U, Sv39 + Svade, mtvec direct, 0 PMP entries, ASIDLEN 0 | The OpenSBI and Linux minimum; add C, then F/D, toward RV64GC |
| Boot ROM | 0x1000: `auipc`/`ld` of a0 = 0 and a1 = DTB address, jump to 0x8000_0000 | As Spike and QEMU |
| DRAM | 0x8000_0000, 64 MiB (32 MiB minimum) | LiteX: "32MB of RAM (reduced to 8MB when rootfs can be put on an SDCard or NFS)" (Fact, https://github.com/litex-hub/linux-on-litex-vexriscv) |
| Load layout | `fw_jump` 0x8000_0000; kernel `Image` 0x8020_0000 (2 MiB aligned); DTB and initramfs near the top | Kernel boot.rst alignment; NaxRiscv's sim uses 0x80000000 / 0x80400000 / 0x80F80000 / 0x81000000 (Fact, https://raw.githubusercontent.com/SpinalHDL/NaxRiscv/main/src/test/cpp/naxriscv/README.md) |
| CLINT | SiFive layout at 0x0200_0000 | OpenSBI timer and IPI driver, and Spike's address |
| Time base | 10 MHz in DT. **Lab time:** mtime = retired instructions / 100, as Spike does | Makes timer interrupts deterministic in instruction count. Model and RTL then agree exactly, with no injection (section 3.1) |
| UART | ns16550a at 0x1000_0000, reg-shift 0, TX to the log, RX from a scripted file | Spike's address; OpenSBI and Linux both have 8250 drivers |
| PLIC | Optional at first. With it: 1 source (UART RX), S and M contexts, at 0x0c00_0000 | A busybox shell over a polled console is plausible (Memory: the 8250 driver polls with a timer when the port has no IRQ; verify). A 1-source PLIC is about 150 lines of RTL, and it removes that risk |
| Finisher | SiFive Test (`sifive,test0`) at 0x0010_0000, as QEMU virt | `poweroff` ends a run with a code. Memory: OpenSBI has a reset driver for it; verify |
| DTB | Project-written `.dts` (MIT), compiled by dtc built from source in `build/third-party/` | Linux and OpenSBI read it |

**Existing minimal reference platforms (Fact unless marked):**

| Platform | ISA / modes | Devices | Notes |
|---|---|---|---|
| QEMU virt | Up to 512 RV64GC harts | CLINT/ACLINT, PLIC/AIA, NS16550, RTC, test, virtio, PCIe, flash | Too rich for us. Its test device and NS16550 are worth copying |
| Spike | Default `rv64imafdc_zicntr_zihpm`, priv `MSU` | CLINT, PLIC, NS16550 (plus HTIF) | Our recommended map. OpenSBI + Linux boots on it (wiki: https://github.com/kvm-riscv/howto/wiki/KVM-RISCV64-on-Spike, not an official RISC-V page) |
| Sail | M/S/U, Sv32/39/48/57, Svade/Svadu, PMP | Spike-like platform: CLINT-style and HTIF console (no console input) | "platform support sufficient to boot Linux, FreeBSD and seL4"; a Busybox boot "takes much longer" (https://github.com/riscv/sail-riscv, https://raw.githubusercontent.com/riscv/sail-riscv/master/os-boot/README.md) |
| LiteX / VexRiscv | RV32IMA with MMU and Supervisor ("VexRiscv linux balanced") | LiteX UART, LiteDRAM, optional Ethernet and SD | 2883 LUT and 2130 FF at 180 MHz on Artix 7 (https://github.com/SpinalHDL/VexRiscv). OpenSBI `PLATFORM=litex/vexriscv` builds `fw_jump.bin`; 32 MB RAM |

---

## 2. How others did it

| Core | What it boots and how it is checked (Fact unless marked) | Lesson for us (Judgement) |
|---|---|---|
| VexRiscv / LiteX | RV32IMA, MMU and S-mode; "the CPU simulation can already boot linux and run user space applications (even python)"; Linux is part of the regression (`VEXRISCV_REGRESSION_LINUX_REGRESSION`) | A Linux-capable core can be small: about 2.9 kLUT on Artix 7. Linux in the regression catches bugs |
| NaxRiscv | RV32/RV64 IMAFDCSU out-of-order; Verilator testbench loads `fw_jump.bin`, `Image`, dtb and cpio; Spike is "used as a golden model during the sim to check the dut behaviour (lock-step)"; the full regression including Linux "will take about 30mn" | **The closest analogue to us:** an OoO core in lockstep with Spike through a whole Linux boot |
| CVA6 (Ariane) | RV64GC, Sv39, "6-stage, single-issue, in-order"; Linux on the Genesys 2 board; Spike installed for verification; riscv-dv random tests (https://github.com/openhwgroup/cva6) | Our pipelined core is CVA6-class. Linux on a single-issue in-order RV64 core is routine |
| XiangShan | NEMU is "the golden model of XiangShan processor" (difftest after each commit); NEMU boots Linux images, generates SimPoint BBVs, then dumps checkpoints (".gz files of memory image") to run on RTL; it should not checkpoint in M-mode; RTL Verilator runs take hours to days (https://github.com/OpenXiangShan/NEMU; HC2024 slides) | **Exactly our sampled-benchmark method, extended to Linux:** a fast ISS boots, takes checkpoints, and the RTL runs windows |
| Rocket / BOOM (Chipyard) | Spike architectural checkpoints (`generate-ckpt.sh`) hold "cacheable memory, core architectural registers, and core CSRs"; RTL loads them with `LOADARCH`. Limits: single core, initramfs only, HTIF console, "can't include a serial device or a block device" (https://chipyard.readthedocs.io/en/main/advanced-concepts/architectural-checkpoints/). Boots Linux on FireSim FPGA simulation (Memory) | Checkpoints must also carry CSRs and device state. Chipyard avoids device state by removing devices. We can carry CLINT and UART state instead |
| SERV | No: bit-serial RV32I, no MMU (Memory) | No |
| Ibex | No: RV32 M/U, PMP, no S-mode or MMU (Memory) | No |

**Boot cost** (Fact, a third-party simulator, not an official source):
https://willmccallion.github.io/rvsim/examples/linux-boot reports one hart from reset to the login
shell (OpenSBI, Linux 6.6, Sv39, Busybox), measured 2026-10-11:

| Model | Instructions retired | Cycles | Cycles in WFI |
|---|---|---|---|
| In-order | 314.8M | 785.1M | 61% |
| Out-of-order | 379.2M | 693.1M | 70% |

Judgement: plan for **0.3-0.5 billion instructions** to a shell, of which most *time* is WFI. Idle
fast-forward therefore matters more than raw speed.

**Our simulation speeds** (Fact, DEVLOG):
- **Multicycle core under Verilator:** "about 6.3M instructions/s" (LZMA d16 to d20 from reset).
- **Out-of-order core:** the d16 whole-program run took 173 s for about 63M instructions (9.09M
  clocks at 6.37 IPC plus 1.62M at 3.19). That is about **0.36M instructions/s**, or 60k clocks/s.
- **rv_iss:** about 150 MIPS (task brief; its header says reference.py runs about 50k instructions/s).

Estimate (Judgement): a 350M-instruction boot, with WFI fast-forwarded, would take:

| Simulator | Time |
|---|---|
| rv_iss, system mode, assuming 30-80 MIPS after adding the MMU | 5-15 s |
| Multicycle core, Verilator, assuming 3-5M instructions/s with privilege | 1-2 min |
| Out-of-order core, Verilator | 16-30 min |
| Icarus | Impractical |

So:
1. Boot in rv_iss, take checkpoints, and run the out-of-order core on sampled windows, as XiangShan
   and Chipyard do.
2. Run full RTL boots on the multicycle core in the regression, as VexRiscv does.
3. Run an occasional full out-of-order boot overnight, as a milestone and not as a gate. That needs
   the user's admission check for long runs (memory: 5-minute run timeouts).

---

## 3. Which core first, and the staged plan

### 3.1 Cross-cutting decisions (Judgement)

1. **One shared contract document**, `cpu/PRIV-CONTRACT.md` (like FP-CONTRACT), written before RTL.
   - It fixes every implementation-defined choice: Svade, ASIDLEN 0, PMP 0, tval rules, SC failure
     conditions, the WFI behaviour, the interrupt boundary rule and lab time.
   - Spike is then configured to match it.
2. **One define per stage**, all default 0: `RV64_PRIV`, `RV64_IRQ`, `RV64_A`, `RV64_SMODE`, `RV64_SV39`
   and `RV64_C`. Each requires its predecessors (an elaboration-time `$error` otherwise).
   - With all of them off, the cores and traces stay byte-identical to the trace lock (roadmap 3.3):
     Dhrystone and 7-Zip probe clocks identical, both cache sizes.
   - With an option built in but unused (M-mode firmware that never traps), benchmark clocks must
     also be identical. This catches a timing leak into the default path.
3. **Shared RTL modules:** `rv64_csr.sv` (CSR file, trap and interrupt arbitration), `rv64_tlb.sv`,
   `rv64_ptw.sv` and `rv64_amo.sv`, written once. The multicycle and pipelined cores instantiate them
   directly. The out-of-order core reuses the CSR and PTW logic behind its own ports.
4. **Deterministic lab platform** for lockstep:
   - mtime = instret/100, the external interrupt raised at an instruction index, and UART RX from a
     scripted file. Then every core, and both models, take each interrupt at the same instruction
     boundary.
   - The out-of-order core must cut a retirement group at that boundary. Cheap: a retire limit.
   - A *real-time* mode (mtime from clocks) is for performance runs. It uses an `I` record that the
     models obey (roadmap 2.11).
5. **Trace additions, only when an option is on:**

| Record | Meaning |
|---|---|
| `E pc cause tval` | A trap taken, not terminal |
| `I pc cause` | An interrupt taken before `pc` |
| `P m` | The privilege mode changed |
| `C csr val` | A CSR write, including the implicit mepc, mcause, mtval and mstatus writes on a trap. The record already exists |
| `N csr val` | A DUT-sourced read; only in real-time mode |
| `T` | Terminal again only through the finisher |

   - PCs in the trace are virtual. `W` gains the physical address (`W va pa bytes`) once Sv39 is on.
   - 16-bit instructions are zero-extended in `insn`, with `next` = pc + 2.
6. **Memory map:** the lab-virt map (DRAM at 0x8000_0000) is a SoC parameter (`LINUX_MAP`). The
   existing 0x0-based map stays the default, so no benchmark image moves.

### 3.2 Order (Judgement)

```
G: rv_iss system mode + Spike + Linux boot (milestone M1, no RTL, no bump)
  -> S1 M-mode CSRs/traps/mret   [MC, then PIPE, then OOO]   (roadmap step 7)
  -> S2 FS/VS (OOO), Zicntr, PMA + CLINT, M interrupts + WFI  (roadmap steps 8-11)
  -> S3 A                        [MC, PIPE, OOO]
  -> S4 U + S modes, delegation, sret, counteren/envcfg
  -> S5 Sv39 TLB + PTW + Svade + SFENCE.VMA + MPRV/SUM/MXR
  -> S6 SoC: lab-virt map, ns16550, 1-source PLIC, finisher, boot ROM
  -> E1 Linux boots on MC RTL (evidence, no bump)
  -> PIPE gets S3-S5 (FPGA Linux path; E2 PIPE boot)
  -> OOO gets S3-S5 (E3 sampled Linux user-space windows)
  -> S7 C on OOO and PIPE (RV64GC claim only on OOO, the only core with F/D)
```

**Why the multicycle core first** (a departure from roadmap 2.6, 2.8 and 2.18):
- It is non-speculative, so precise traps, interrupts and MMU faults are simplest. It becomes the RTL
  reference the other cores are compared with.
- Verilator runs it at about 6.3M instructions/s, so a **whole Linux boot in RTL takes minutes**. That
  is the strongest end-to-end evidence, and it arrives soonest.
- It needs no C. Its dual/triple pairing can stop at SYSTEM, AMO and CSR instructions.

The cost: the multicycle core carries `rv64ima_zicsr_zifencei` + Sv39. It is **not RV64GC**, because it
has no F/D, and adding C would break its pairing rules (roadmap 2.8). Alternative: start on the
pipelined core if the council values the FPGA path over early evidence. Its RTL simulation is a few
times slower (not measured).

**Why the S track moves forward** (a departure from roadmap step 26+): the user's flag makes the
execution environment the priority. Zicclsm, the CBOs, Zfhmin, full V and Supm do not block Linux.
Steps 3-6 of the roadmap (Zicond, Zfa, Zimop, hints) can still interleave, because they are S-sized.

### 3.3 Stages

Effort: S ≤ 1 agent-session, M = 1-3 days, L = 3-7 days, XL > 1 week. All Judgement. Each line is its
own MINOR with tag, history row, DEVLOG entry, regression at both cache sizes and a logged Dhrystone
(AGENTS.md). A stage on a second or third core is its own MINOR.

| Stage | What | Trace contract | Golden-model work first | Tests that prove it | Effect when off | Effort |
|---|---|---|---|---|---|---|
| **G** (no bump) | rv_iss `--sys`: M/S/U, Sv39, A, C, CLINT, UART, PLIC, finisher, lab time, WFI fast-forward, state v3; Spike built from source; OpenSBI + Linux + busybox built from source | Defines the records above (models only) | This *is* the model work | riscv-tests rv64mi/si/ua/uc and the `v` env (all of rv64ui under Sv39 with demand paging; riscv-test-env `v`, Memory) on rv_iss; rv_iss against the Spike commit log on those tests and the first 50-100M instructions of the boot; a boot log to the shell | None: new flag | L-XL (section 5) |
| **S1** M-mode | Full Zicsr, the M CSRs, mtvec direct (vectored optional), the trap jump, mret, WFI as a no-op, exception priority, illegal CSR; test end via the finisher or mailbox | `E`, `C`, `P`; `T` no longer terminal on a trap | reference.py: M subset (the only privileged part it gets); rv_iss already done in G | Directed: every cause through a handler and back; nested traps; WARL fields; riscv-tests rv64mi with the stock `p` env; Spike lockstep | Zero (define off; trace lock) | MC M, PIPE M, OOO L (CSRs serialise at the ROB head; trap = flush + redirect; mret = serialising jump) |
| **S2** | FS/VS live (OOO), Zicntr, PMA (MMIO uncacheable, non-speculative, no fetch), CLINT in the SoC, M interrupts, real WFI | `I`; `N` in real-time mode only | rv_iss (G); Spike runs with the same `INSNS_PER_RTC_TICK` | Pending IRQ during memory stalls and split reads; take within K; MMIO never cached or over-read (check_soc_memory) | Zero | M each, already in the roadmap (8-11) |
| **S3** A | LR/SC (one reservation, 8 B, or 64 B for Za64rs) and AMOs .W/.D with aq/rl | AMO: `W` then the rd value; SC: `W` only on success; SC failure only for contract-listed reasons (no reservation, mismatch, intervening trap, interrupt or own store) | reference.py + rv_iss (roadmap 2.6) | riscv-tests rv64ua; LR/SC with traps and interrupts in between; OOO: AMO against younger loads, stores to the reserved line | Zero (opcode 0x2f stays cause 2) | MC S-M, PIPE M, OOO M (AMOs at retirement, non-speculative, holding the bus; LR sets the reservation at retirement; SC's rd known only at retirement) |
| **S4** S/U | U and S modes, medeleg/mideleg, sret, sstatus/sie/sip views, mcounteren/scounteren, menvcfg/senvcfg, TW/TSR/TVM, ecall causes 8/9 | `P` values u/s/m; delegated `E` | rv_iss (G); reference.py not extended (Spike covers it) | riscv-tests rv64si; privilege rejection (S/U access to M CSRs, sret in U, TSR/TVM/TW); delegation matrix; Spike lockstep | Zero | MC M, PIPE M, OOO M-L |
| **S5** Sv39 | ITLB/DTLB (for example 16-32 entries, fully associative), a PTW reading through the D-side, Svade faults, superpages, SFENCE.VMA (flush all), MPRV/SUM/MXR, satp WARL (Bare/Sv39 only, so Linux falls back from Sv48) | Virtual PCs; `W va pa`; page faults as `E` 12/13/15; `C satp` | rv_iss (G); Spike configured `--isa ... _svade`, no Svadu | riscv-tests `v` env (all of rv64ui virtualised) and rv64si `dirty`; ACT `priv` Sv/Svade/Svbare (when ACT runs); superpage misalignment faults; SFENCE after a PTE store; fetch across a page boundary | Zero (with the define off, satp access is cause 2, as for any unimplemented CSR) | MC M-L, PIPE L, **OOO L-XL** |
| **S6** SoC | `LINUX_MAP`: boot ROM, 64 MiB DRAM, ns16550, 1-source PLIC, finisher, lab time | MMIO reads deterministic in lab mode | rv_iss device models are the reference | check_soc_memory cases for each device; OpenSBI banner on the multicycle core | Zero (default map unchanged) | M |
| **E1/E2** (no bump) | Linux to a shell on MC (and later PIPE) RTL, in lockstep with rv_iss | none | none | Boot log identical to rv_iss's (lab time makes it bit-exact); DEVLOG instruction and clock counts | n/a | S-M of debugging per core; Judgement: expect real bugs |
| **E3** (no bump) | OOO runs post-boot user-space windows (QuickJS, 7-Zip built for Linux) from rv_iss checkpoints | none | Checkpoint v3 + an M-mode restore stub | Window traces match rv_iss; sampled IPC against the bare-metal port | n/a | M |
| **S7** C | Zca + Zcd (OOO), Zca (PIPE) | 16-bit `insn`, `next` = pc + 2; cause 0 disappears | reference.py + rv_iss expander (rv_iss already has it from G) | Exhaustive 65,536-parcel decode walk against Spike's decoder; straddling at beats, lines and pages (an ITLB miss on the second half); rv64uc; SMC over C code | Zero | PIPE M, **OOO L** (roadmap 2.8) |

**The out-of-order core, realistically** (Judgement):
- **Precise interrupts:**
  - Take an interrupt only at the ROB head, after the trap drain rule (section 3: no split read
    outstanding). Store writes already happen at retirement, so nothing younger is architecturally
    visible.
  - Interrupt latency is bounded by the oldest in-flight memory miss. Bound it (K) in the contract.
- **TLB misses mid-window:**
  - The DTLB is looked up at address generation. A miss allocates one PTW (or 2-4). Its PTE reads go
    through the existing split-read miss path.
  - A page fault is recorded in the ROB entry and raised only at retirement.
  - Svade means the PTW never writes, so speculative walks are harmless.
  - The walker need not snoop the store queue: SFENCE.VMA is the ordering point (Fact, 1.3). Even so,
    a PTE store retires to memory before the SFENCE completes, so SFENCE.VMA = drain stores + flush
    TLBs + refetch.
  - satp writes and SFENCE.VMA serialise, as fcsr writes do.
  - The ITLB gets one lookup per 32-wide fetch group, cut at a 4 KiB page crossing (one more cut
    rule).
  - The 0.15.6 load-wait table, value prediction and MDP are PC-indexed. PCs stay virtual, so they
    keep working. ASID 0 means flush on switch.
  - State the TLB port count as a behavioural assumption, as FP write-back is today.
- **LR/SC and AMOs:**
  - Both are non-speculative at retirement and need a blocking read.
  - The reservation is cleared by any trap or interrupt (deterministic).
  - Younger loads to the same 8 bytes are caught by the existing memory-order-violation check if the
    AMO is treated as a store whose address is known at issue.
  - The cost is a serialisation per AMO. Linux spinlocks and atomics are rare in user benchmarks.
- **C in a 32-wide front end:**
  - Do not length-decode 64 parcels serially at fetch. Instead, pre-decode at I-cache fill: store one
    "instruction starts here" bit per 16-bit parcel, plus a 2-mod-4 carry-in per beat.
  - Extract 32 instructions per clock with a prefix-sum over the start bits.
  - Expand C to 32-bit before rename, so the 0.12.3 folding still applies.
  - Every predictor index must take PC bit 1. The BTB `btb_fits` and offset encoding (0.15.5) change.
  - **Expected gain about 0 on the behavioural model** (roadmap 4.2). C is for compatibility, so it
    goes last.
- **Effort:** the out-of-order core needs S1-S5 in about 4-6 weeks of agent time (Judgement), with a
  Codex review at each step. The 512-entry ROB makes interrupt-latency tests long.

---

## 4. Golden models: recommendation (Judgement)

| Option | Pros | Cons |
|---|---|---|
| A. Extend reference.py **and** rv_iss to full system | Keeps the two-model rule; everything in our trace format | Two copies of a large privileged and MMU spec by the same authors share mistakes (architecture.md 8). reference.py at about 50k instructions/s cannot boot Linux (2 hours for 350M). About 2x the work |
| B. Adopt Spike (or Sail) as the only privileged model | Independent, widely used for lockstep (NaxRiscv, CVA6, Chipyard); boots OpenSBI + Linux; Svade/Svadu, PMP, Sm1p13/Ss1p13 | No state-file or checkpoint format of ours; its trace must be converted; C++ build; it cannot produce our sampled windows; platform changes need a C++ patch |
| **C. Recommended:** rv_iss = system-mode workhorse; **Spike = privileged authority**; Sail = arbiter and ACT; reference.py = user-mode authority + M-trap subset | Fast boot and checkpoints in our own format (bench_checkpoint.py, RVISSST states, warm caches); independence where it matters; Spike's map and RTC rule adopted, so the same DTB and images run on both | rv_iss is no longer checked against reference.py for S/U/MMU, only against Spike; a converter from Spike `--log-commits` to our trace (M) |

Details for C:
- **Build and lock:** build Spike (BSD-3) and Sail (BSD-2) from source in `build/third-party/` with a
  lock file holding commit and tree SHA-256. Never vendor them. Record each run in DEVLOG.
- **Configure Spike to match PRIV-CONTRACT:** ISA string, `--priv=msu`, Svade, PMP 0 (memory: Spike
  has a `--pmpregions` option), the same DRAM size, and the DTB passed with `--dtb`.
- **Lockstep scope:** compare full traces on all directed and riscv-tests programs. On the Linux boot,
  compare the first N instructions plus sparse state hashes (pc, x1-x31 and the CSRs every 1M
  instructions). Spike's interleave (`INTERLEAVE = 5000`) does not matter for one hart.
- **Where Spike and the contract may disagree:** where Spike's implementation-defined choices differ
  (tval on fetch faults across pages, misaligned AMO cause, WFI), the contract follows the spec and
  the discrepancy goes on a list. Sail arbitrates.

---

## 5. First milestone M1 (Judgement)

**Goal:**
- rv_iss `--sys` boots OpenSBI `fw_jump` + Linux + a busybox initramfs on lab-virt to a `/ #` prompt.
- It runs a scripted command (for example `echo ok; poweroff`) from the UART RX file.
- It matches Spike's commit log over the agreed window.
- It writes full-system checkpoints from which a user-space benchmark continues.

**Work:**

| Item | Size |
|---|---|
| rv_iss: CSR file (about 45 CSRs), traps and delegation, interrupts, mret/sret/wfi/sfence.vma | about 600 lines |
| rv_iss: Sv39 walker with Svade + a software translation cache for speed (flushed on satp and SFENCE writes) | about 300 lines |
| rv_iss: A | about 100 lines |
| rv_iss: C expander | about 250 lines |
| rv_iss: CLINT, ns16550, 1-source PLIC, finisher, boot ROM | about 350 lines |
| rv_iss: WFI fast-forward (advance mtime to mtimecmp, deterministic) | |
| rv_iss: state v3 "RVISSST3" (CSRs, mode, devices; the reservation is dropped, which is legal: SC may fail) | |
| rv_iss total | about 2,000 lines of C, MIT; L |
| Third-party builds in `build/third-party/linux-lab/`, all from source with a lock file. Clang 23 is present; Linux `LLVM=1`, OpenSBI `LLVM=1` (both supported upstream) | M |
| ... OpenSBI (BSD-2) | |
| ... Linux (GPL-2.0), a tinyconfig + MMU/TTY/8250/initramfs fragment, `CONFIG_RISCV_ISA_C` on and `FPU` off at first | |
| ... musl (MIT) and busybox (GPL-2.0), static | |
| ... dtc (GPL-2.0/BSD-2 for libfdt) | |
| ... initramfs via the kernel's `gen_init_cpio` | |
| ... **No GPL file enters the repository.** We commit only our scripts, DTS, kernel config fragment (our text) and lock file. A storage and runtime admission check comes first (AGENTS.md); judgement: a few GB of sources and objects, minutes to build | |
| Spike build + log converter + lockstep driver; riscv-tests rv64mi/si/ua/uc and `v` env on rv_iss and Spike | M |
| Restore stub v3 for RTL (M-mode: write the CSRs, set mtimecmp and the UART state, set mepc/MPP, then mret) and a checkpoint taken after `init` starts a benchmark | S-M |
| **M1 total** | **about 2-3 weeks of one agent plus reviews**; no RTL, so no version bump; DEVLOG entries per run |

**What M1 unlocks:**
1. PRIV-CONTRACT can be written against a running model.
2. S1-S6 on the multicycle core have an oracle and a boot image on the first day.
3. The out-of-order core can run user-space benchmarks under Linux in sampled mode as soon as it has
   S1-S5. Real `7z b` built for Linux is then the authentic form of the current 7-Zip goal
   (`cpu/7zip-benchmark-targets.md`), with the kernel's page-table and TLB behaviour included.

---

## 6. Main risks (Judgement)

1. **The trace contract and determinism.**
   - Interrupts and MMIO make the "two independent runs" comparison impossible without lab time or
     injection.
   - Design it once in PRIV-CONTRACT (section 3.1). Getting it wrong spreads to every core.
2. **Out-of-order complexity:** TLB/PTW in the speculative LSU, serialising CSRs, satp and SFENCE.VMA
   in a 512-entry ROB, interrupt latency, AMO ordering against MDP and value prediction, and C in the
   32-wide fetch. This is the place for a Codex review at every step.
3. **Benchmark identity:** every define off must hold the trace lock and clocks. The "built in but
   unused" check is where timing leaks show.
4. **Simulation cost:** Icarus is unusable for boots. Out-of-order full boots take tens of minutes and
   conflict with the 5-minute run preference. Checkpoints are mandatory there.
5. **Licences:** GPL sources only in ignored `build/third-party/`, built from source, never vendored.
   DTS and config fragments are our own text. The binary-download rule rules out prebuilt images and
   toolchains.
6. **Scope creep and naming:**
   - This is an "S-mode + Sv39 Linux experiment" until RVA23S64 items, H included, exist.
   - The multicycle and pipelined cores are `rv64ima`, not RV64GC. Only the out-of-order core can
     claim RV64GC after S7.
7. **Reference disagreements:** Spike's implementation choices against the contract; Sail is the
   arbiter.
8. **Opportunity cost:** about 2-3 weeks for M1 and 6-10 more for all three cores. The work diverts
   agents from the 7-Zip IPC loop. M1 + E3 is the cheapest route that serves both goals.
9. **Facts marked Memory:** check them before the contract:
   - 8250 polling without an IRQ;
   - OpenSBI `sifive,test0` reset;
   - OpenSBI CSR probing;
   - riscv-test-env `v`;
   - Spike `--pmpregions`;
   - SERV, Ibex and FireSim.

## 7. Sources fetched (2026-11-22)

Linux:
- https://docs.kernel.org/arch/riscv/boot.html
- https://raw.githubusercontent.com/torvalds/linux/master/arch/riscv/Kconfig
- https://raw.githubusercontent.com/torvalds/linux/master/arch/riscv/Makefile
- https://docs.kernel.org/arch/riscv/uabi.html
- https://docs.kernel.org/arch/riscv/hwprobe.html
- https://docs.kernel.org/arch/riscv/vm-layout.html
- https://raw.githubusercontent.com/torvalds/linux/master/arch/riscv/mm/init.c
- https://raw.githubusercontent.com/torvalds/linux/master/Documentation/devicetree/bindings/riscv/cpus.yaml
- https://raw.githubusercontent.com/torvalds/linux/master/drivers/tty/hvc/Kconfig

RISC-V specifications:
- https://github.com/riscv/riscv-isa-manual/blob/main/src/priv/supervisor.adoc
- https://github.com/riscv/riscv-aclint/blob/main/riscv-aclint.adoc
- https://docs.riscv.org/reference/sbi/v3.0/ext-base.html
- https://github.com/riscv-non-isa/riscv-sbi-doc/blob/master/src/binary-encoding.adoc

OpenSBI:
- https://raw.githubusercontent.com/riscv-software-src/opensbi/master/docs/platform_requirements.md
- https://raw.githubusercontent.com/riscv-software-src/opensbi/master/docs/firmware/fw.md
- https://raw.githubusercontent.com/riscv-software-src/opensbi/master/docs/platform/generic.md
- https://raw.githubusercontent.com/riscv-software-src/opensbi/master/lib/sbi/sbi_emulate_csr.c
- https://github.com/riscv-software-src/opensbi/tree/master/lib/sbi

Reference models:
- https://github.com/riscv-software-src/riscv-isa-sim
- https://raw.githubusercontent.com/riscv-software-src/riscv-isa-sim/master/riscv/platform.h
- https://raw.githubusercontent.com/riscv-software-src/riscv-isa-sim/master/riscv/sim.h
- https://raw.githubusercontent.com/riscv-software-src/riscv-isa-sim/master/LICENSE
- https://github.com/riscv/sail-riscv
- https://raw.githubusercontent.com/riscv/sail-riscv/master/os-boot/README.md

Platforms and other cores:
- https://www.qemu.org/docs/master/system/riscv/virt.html
- https://github.com/litex-hub/linux-on-litex-vexriscv
- https://github.com/SpinalHDL/VexRiscv
- https://raw.githubusercontent.com/SpinalHDL/NaxRiscv/main/src/test/cpp/naxriscv/README.md
- https://spinalhdl.github.io/NaxRiscv-Rtd/main/NaxRiscv/simulation/index.html
- https://github.com/openhwgroup/cva6
- https://github.com/OpenXiangShan/NEMU
- https://chipyard.readthedocs.io/en/main/advanced-concepts/architectural-checkpoints/

Third-party, not official:
- https://willmccallion.github.io/rvsim/examples/linux-boot (boot instruction counts)
- https://github.com/kvm-riscv/howto/wiki/KVM-RISCV64-on-Spike

Repository facts:
- `cpu/architecture.md` sections 1, 3, 4, 5, 6 and the 0.17.x history.
- `sim/cpu/bench/rv_iss.c` header: state files and `--dump-at`.
- `sim/cpu/bench/bench_checkpoint.py`: the restore stub, "no CSRs, no reservations".
- DEVLOG: Verilator speeds.
- `rtl/cpu/rv64_bram_soc.sv` parameters.
