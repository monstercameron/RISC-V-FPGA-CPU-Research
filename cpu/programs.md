# Study programs for the CPU

The visualizer contains seven lessons in increasing conceptual complexity. Select a **Study program** or use **Previous lesson / Next lesson** to load its verified run immediately. **Run simulation** recompiles the selected C file and executes it on the custom RTL core. The C, Assembly and Binary views, circuit, registers and output all switch together.

Every lesson has two things to watch, a question with a revealable explanation, and a **Go to** menu of actual execution events. Use **Step instruction** for program flow and **Step clock** for RAM waits. **Jump to output** reveals the completed result; **Reset** lets you study it again.

Use the [Program inputs panel](inputs.md) to view and edit each lesson's starting data. Run again to update the code, capture and outputs. The table below records the default inputs.

## The progression

| Level | Program | What to study | Verified output | Clocks | Instructions retired |
|---:|---|---|---|---:|---:|
| 1 | [1 + 1](../sim/cpu/add_one.c) | Inputs, ADD, register write, output store | 2 | 48 | 13 |
| 2 | [Make a decision](../sim/cpu/programs/decisions.c) | Signed comparison and both paths of one branch | 7, 14 | 108 | 31 |
| 3 | [Count and accumulate](../sim/cpu/programs/counting.c) | Counter, running sum, backward branch and exit | Sum 55; count 10 | 230 | 67 |
| 4 | [Read an array](../sim/cpu/programs/arrays.c) | Eight-byte element addresses, loads, negative values | Sum 20; minimum -3; maximum 12 | 270 | 83 |
| 5 | [Functions and the stack](../sim/cpu/programs/calls.c) | Recursion, return addresses, stack saves and restores | T(5) = 15 | 309 | 84 |
| 6 | [Sort six numbers](../sim/cpu/programs/sorting.c) | Nested loops, comparisons and array writes | 1, 2, 3, 5, 7, 9 | 935 | 268 |
| 7 | [Sort, Fibonacci & CRC32](../sim/cpu/c_demo.c) | Combined algorithms, bit shifts and XOR | Sum 1242; Fibonacci 102334155; CRC32 0x97f65c54; full results in viewer | 69,157 | 22,674 |

These are measured clocks for the present multicycle core and RAM adapter, including startup and terminal EBREAK. They are not host runtime, FPGA frequency, or a promise that more complex source always needs more clocks. The final EBREAK does not retire as a normal instruction.

## Suggested experiments

1. **Addition:** jump to **The ADD instruction**. x11 already holds 2, but the output is pending. Step toward **First output write** and watch RAM receive it.
2. **Decision:** compare **Decision: branch taken** and **Decision: branch not taken**. The instruction address is identical; its input value and next address differ. The compiler uses a branch for the nonnegative path, so a taken machine branch is not necessarily the C `if` body.
3. **Loop:** compare **Loop: go around again** with **Loop: final exit**. Watch the next PC move backward or fall through. The volatile limit is deliberately reread so the compiler retains a real loop instead of replacing it with a formula.
4. **Array:** visit **First data load** and **Load the next address**. Switch registers between decimal and hex to see -3 as `0xfffffffffffffffd`. Step backward from a completed load to inspect its RAM wait.
5. **Calls:** inspect x1 (`ra`) and x2 (`sp`), then visit stack-save, call, recursive-call and return checkpoints. The noinline function and volatile local preserve real calls and stack traffic. This is six invocations of `triangular`, including the base case at zero.
6. **Sorting:** jump to **Move an array element**. The bus is writing working memory while the output is still pending. Later a separate loop copies the sorted values to the output mailbox.
7. **Combined demo:** jump between sorting, Fibonacci and CRC32. Use fast playback for an overview, then slow down or step individual instructions within one algorithm.

All outputs use 64-bit RAM words starting at `0x3000`; there is no OS or printf driver. Returning zero means the program's own checks passed. The arithmetic results are shown separately in the mailbox.

## Rebuild and run

From the project root, rebuild every lesson and its evidence:

```powershell
python -B sim/cpu/build_programs.py
.\sim\cpu\run_visualizer.ps1
```

The launcher builds the library if saved lesson captures are missing. The suite leaves the addition lesson as the initial page. To rebuild one program:

```powershell
python -B sim/cpu/build_visualizer.py --program calls
```

Allowed IDs are `add`, `branch`, `loop`, `array`, `calls`, `sort`, and `demo`. The builder uses the existing LLVM and Icarus/WSL installation; no packages or paid services are added. Linux users can run the Python scripts directly with LLVM/LLD and Icarus installed. Both builders accept tool-path and WSL distribution overrides.

Each lesson's saved data, ELF, binary, disassembly, binary instruction listing, and trace live in ignored `build/cpu/programs/<id>/`. The current run also lives in `build/cpu/visualizer/`. Rebuilding one lesson preserves the other saved lessons. The standalone HTML embeds only the active lesson; opening it as a file supports that replay, while switching lessons and starting simulations require the local server.

## Evidence and limits

The [catalog](../sim/cpu/program_catalog.py) owns the source choices and study text. The [input module](../sim/cpu/program_inputs.py) owns editable defaults, bounds, generated source and input-specific expected answers. [The builder](../sim/cpu/build_visualizer.py) compares every retired instruction, accepted RAM write and trap against the sequential ISA reference, checks the final mailbox and return status, and verifies debug symbols do not alter executable bytes. Every required checkpoint must exist for the default inputs. Custom inputs can omit paths; their absent checkpoints are recorded and shown in the UI. This catches optimizations that remove the behavior a lesson intends to teach.

[The suite verification record](programs-verification.json) captures all seven runs and their source, firmware and trace identities. It records the last full suite run; individual reruns update their per-program records and [the active run's record](visualizer-verification.json). C-line highlighting follows optimized compiler debug attribution, so source lines can appear out of order. Use assembly and clock events for precise execution order.

This is RTL simulation and replay of the current RV64I/FENCE.I core. No physical FPGA run, full RVA23 compliance, or official ISA certification is implied.
