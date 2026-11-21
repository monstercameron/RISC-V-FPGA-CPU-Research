# Watch the C program execute

The visualizer is connected to the actual project simulator. Its **Run simulation** button compiles the selected C program, runs Icarus against our CPU and synchronous RAM RTL, verifies the execution, then loads the new clock capture. It does not synthesize an animation from expected answers.

Choose among [seven progressively more involved study programs](programs.md): addition, decisions, counting loops, arrays, recursive calls, sorting, and the combined Fibonacci/CRC32 demo. Selection immediately loads the saved verified run. Each lesson includes study notes, a question with a revealable explanation, and checkpoints grounded in actual executed instructions or bus events.

The [addition walkthrough](addition.md) includes C source, compiled assembly and binary instruction words. Every lesson has the same three code views; the hardware pane always shows the current instruction's bits, hexadecimal word and little-endian RAM bytes.

From the Desktop project root:

```powershell
.\sim\cpu\run_visualizer.ps1
```

This starts a small Python server on an available loopback port and opens the connected viewer in your browser. Keep that command running while using Run simulation. Ctrl+C closes the connection. You can specify `-Port` or `-NoOpen`; otherwise the launcher chooses an available port and prints its URL. The server runs the C source and RTL in **that project folder**. The evidence panel identifies the connected folder.

The existing LLVM, Python, Ubuntu 24.04 WSL, Icarus and vvp installation is used. No Node packages, GPU, paid tools or remote services are needed to use it. On Linux with LLVM/LLD and Icarus installed, use `python3 -B sim/cpu/build_programs.py` followed by `python3 -B sim/cpu/serve_visualizer.py`.

## Controls

Use the [editable input panel](inputs.md) to inspect or change the selected program's starting data. The displayed-run input record stays separate from the editor until a fresh simulation passes.


- **Study program / Previous lesson / Next lesson:** load a saved verified lesson, including its source, study notes, checkpoint list and outputs. Selection does not run the compiler.
- **Program inputs:** edit the lesson's numbers, arrays, limits or message; **Restore lesson defaults** fills the default values. Drafts survive lesson switching in the current page.
- **Run with these inputs / Run simulation:** compile and execute the selected built-in C program using the entered values. The page shows simulator progress, blocks duplicate runs, and loads a new verified capture on success. If the run fails, its log is available and the last good capture remains visible.
- **Play / Pause:** replay the loaded capture. Overview finishes the long loops quickly; Slow exposes individual clocks. Playback speed affects only the presentation. Fast playback skips displayed frames, while all recorded clocks remain available for inspection.
- **Step instruction:** advance through the next instruction's completion, including memory waits.
- **Step clock / Back / timeline:** move forward or backward through actual sampled clocks. Registers, memory and output rewind together.
- **Go to:** jump to that lesson's observed events, such as a taken branch, loop exit, stack save, recursive call, or output write. The combined demo also has algorithm chapters.
- **C source / Assembly / Binary:** show the compiler-attributed C line, decoded assembly or the actual 32-bit instruction word. Optimized source locations can jump between lines and are not a source-language interpreter.
- **Register values:** inspect all 32 registers in signed decimal or hexadecimal; select one for full signed, unsigned and hexadecimal values.
- **Jump to output:** show the completed program and its verified mailbox values.

Outputs remain pending until the actual RAM write occurs. The completion indication waits until EBREAK and matching results. There is no printf driver: the viewer decodes the lesson's 64-bit output words, starting at `0x3000`.

## What the circuit shows

The diagram groups the program counter, decoder, register file, ALU, control and RAM. Its highlights follow the RTL's actual FETCH, EXECUTE, MEMORY and terminal states. This is a multicycle core with one instruction at a time, not a conventional five-stage overlapping pipeline.

For each clock, the capture records control state, PC, instruction, ALU operands/result, address, read/write data, byte enables, request/response signals, retirement and trap. The drawing shows inputs **before** the rising edge; displayed register and memory values include effects **after** that edge. Since architecture 0.2.2 the RAM wrapper writes on the edge that ends the clock in which a write is presented and acknowledges it in that clock; reads are acknowledged one clock later. Instructions that hit the instruction cache skip FETCH, so most clocks show EXECUTE.

The picture is a functional explanation of the RTL, not a placed FPGA netlist or live physical-board telemetry. Browser playback is a replay. A new click on Run simulation starts a fresh external RTL run; stepping the replay does not step a still-running simulator process.

## Reproducibility and evidence

[The capture testbench](../sim/cpu/tb_visualizer.sv) observes the original CPU and RAM without changing synthesizable logic. [The builder](../sim/cpu/build_visualizer.py) records all clocks and compares every retirement, write and trap against the existing sequential reference. It also checks the selected program's mailbox words and `main`'s return register. Debug symbols used for the C mapping are verified to leave machine-code bytes unchanged.

With default inputs on architecture 0.4.0, the larger demo captures **22,859 clocks** (69,157 on 0.1.0), **22,674 retired instructions**, **90 RAM writes**, and **22,765 matching reference events**. Addition captures **32 clocks** (48 on 0.1.0), **13 retired instructions**, one write and **15 matching reference events**, including an observed ADD of 1 and 1 producing 2. See [the active capture's identities](visualizer-verification.json) and [the addition record](addition-verification.json). This is local verification using a project-authored reference, not official ISA certification. The earlier [C demo report](c-demo.md) describes the larger workload and uninstrumented simulation cost; clock capture adds file output and viewer preparation overhead.

The [HTML template](visualizer.template.html), builder, [connection server](../sim/cpu/serve_visualizer.py) and [launcher](../sim/cpu/run_visualizer.ps1) are maintained source. The generated `cpu/cpu-visualizer.html` is ignored by Git and contains the capture for standalone replay. The launcher checks the saved lesson library and viewer against their current sources, and rebuilds all seven programs if they are missing or stale. You can also generate it directly:

```powershell
python -B sim/cpu/build_visualizer.py
```

Add `--program add`, `branch`, `loop`, `array`, `calls`, `sort`, or `demo` (the command-line default). Build all lessons with `python -B sim/cpu/build_programs.py`; its [suite report](programs-verification.json) records every program. Per-program captures and compiled artifacts are retained under `build/cpu/programs/<id>/`. A `#addition` URL fragment opens an addition capture at the actual ADD clock.

Raw clock data, debug ELF/disassembly, build metadata and the viewer data are under ignored `build/cpu/visualizer/`. For a UI-only edit, `--reuse-capture` verifies source/artifact hashes before reusing the capture. `--capture-only` produces the verified data without building HTML.

Opening the generated HTML directly works offline for replay. Lesson switching and Run simulation are disabled until it is served through the local connection; the embedded active lesson still plays offline. The server binds only to `127.0.0.1`, accepts only the fixed project build command with one of the seven choices in the shared program catalog, and checks same-origin requests and a per-session token. It does not accept uploaded C or arbitrary shell commands. The input module validates bounded JSON input values and computes the corresponding expected answers. Edited runs can have different clock counts or unvisited checkpoints. Changing a workload's algorithm requires updating `sim/cpu/program_inputs.py` and the study catalog, then rerunning the checks.
