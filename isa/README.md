# RVA23 assembly examples

Companion to the [operation mapping](../llm-accelerator/plan/llm-rva23-mapping.md). Original MIT-licensed examples, checked with LLVM 23.1.3 on October 23, 2026. These are relocatable assembly objects, not a bootable program, complete model, driver or qualified numerical implementation.

| Source | Callable examples / purpose | ISA target |
|---|---|---|
| [scalar_ops.S](scalar_ops.S) | Ordered BF16-input FMA dot; separate FP32 multiply/add dot; RMS inverse scale | RVA23U64 |
| [rvv_ops.S](rvv_ops.S) | BF16-input GEMV using integer widening and FP32 vector FMA; separate-operation Delta row update | RVA23U64 |
| [bf16_optional.S](bf16_optional.S) | Native BF16 widening GEMV; scalar RNE BF16 conversion | RVA23U64 + Zfbfmin + Zvfbfmin + Zvfbfwma |
| [transport.S](transport.S) | One-shot ABI command-mailbox submission example | RVA23U64 |
| [opcode_examples.S](opcode_examples.S) | 23 labeled instruction encoding specimens; **not callable** | RVA23U64 plus BF16 options |

## Build and inspect

From the repository root, with Python 3.11+, clang and llvm-objdump on PATH:

```sh
python -B isa/verify_assembly.py
```

Explicit Windows paths, if needed:

```powershell
python -B isa/verify_assembly.py --clang "C:\Program Files\LLVM\bin\clang.exe" --objdump "C:\Program Files\LLVM\bin\llvm-objdump.exe"
```

The script assembles five units, disassembles them, checks 23 words against instruction-field definitions, and requires the base-profile build to reject the optional BF16 instructions. Objects, disassembly, negative-build diagnostics and JSON go into ignored `build/rva23-assembly/`. It downloads nothing. Compiler support for the profile names and BF16 mnemonics is required. A missing tool or unsupported extension is a failed build check, not a skipped pass.

Single-file equivalent:

```sh
clang --target=riscv64-unknown-elf -march=rva23u64 -mabi=lp64d -c isa/rvv_ops.S -o rvv_ops.o
clang --target=riscv64-unknown-elf -march=rva23u64_zfbfmin_zvfbfmin_zvfbfwma -mabi=lp64d -c isa/bf16_optional.S -o bf16_optional.o
llvm-objdump -d bf16_optional.o
```

LLVM accepts profile names in `-march`; this selects instruction availability, not proof that a hardware implementation conforms to the entire profile. [LLVM RISC-V usage](https://llvm.org/docs/RISCVUsage.html).

## Calling and numerical boundaries

- The functions use the standard scalar LP64D calling convention: pointers/counts in `a*`, float arguments/results in `fa*`. They modify caller-saved integer/FP/vector registers and `vl`/`vtype`; they do not use a vector calling-convention variant. Call with `vstart=0`, enabled FP/vector state, valid aligned memory and nonoverflowing buffer extents. They are leaf functions with no stack or runtime dependencies.
- Scalar arithmetic explicitly selects RNE. Vector functions save `frm`, select RNE, restore `frm` on normal return, and leave sticky `fflags` accumulated. They do not implement the command-level flag collection, nonfinite handling, traps or cancellation contract.
- The dots accept zero length and return +0. Both GEMVs accept M=0 (no stores) and K=0 (zero FP32 outputs). `rms_inverse_fp32` requires **1 <= n <= 2^24**, finite data and a suitable positive epsilon; it does not validate inputs. The caller supplies the frozen epsilon bits. Returned norm scale still needs affine operations and casts.
- GEMV input is BF16 `W[K][M]`, x[K]; output is FP32 y[M]. Each vector lane accumulates one output in increasing K. These examples stop **before bias addition and BF16 output rounding**. They therefore demonstrate the projection's inner recurrence, not its complete graph boundary. W and x remain unchanged; y must not overlap either.
- The illustrative K-major weight view differs from checkpoint output-first tensors and does not amend the existing hashed packed layout. Production needs a bounded, versioned tile packer consistent with the layout contract. Repacking may stream small tiles; never allocate the entire model in FP32. Benchmark the layout before selecting it.
- Delta row updates consume a delta already computed from the complete decayed-state prediction. They cannot be interleaved with unfinished prediction reads. Exact old/new aliasing is allowed, other overlap is not. Readout follows the complete update and uses the new state.
- `try_submit_command` assumes a trusted caller holds the driver lock and has completed session, registration, upload/seal, descriptor validation and OS DMA synchronization. It uses aligned 32-bit mailbox accesses under an equivalent platform I/O mapping. Real OS ports use their prescribed MMIO accessors. Return 0 means a doorbell was issued; terminal completion, weight servicing, cancellation and quarantine are still required by the [ABI](../llm-accelerator/plan/abi-v1.md) and [adapter](../llm-accelerator/plan/adapter-v1.md).

## Verification still required

Assembly/encoding checks passed. No QEMU/Spike executable was found on the inspected Ubuntu-24.04 WSL PATH; these kernels were **not executed** on a RISC-V simulator or hardware. No numerical, performance or full-model pass is claimed.

Before integration, add a RISC-V execution harness with independent arithmetic results: K/M in {0,1,VL-1,VL,VL+1}; several VLENs; signed zeros, subnormals and exceptional inputs; adversarial FMA-versus-separate cases; ordered-cancellation cases; exact packing indices; output canaries; `frm` restoration and accrued flags. Compare scalar and vector recurrences against the independent policy oracle, then apply every required graph-boundary cast. Test MMIO submission separately against the ABI simulator, including busy/offline and visibility faults. An ISA simulator checks software semantics; it does not measure FPGA cycles or memory bandwidth.
