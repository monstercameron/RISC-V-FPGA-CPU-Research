# See and edit program inputs

Use the **Program inputs** panel above the study guide. It shows the selected program's numbers, arrays and other starting data.

1. Change one or more fields. Arrays accept commas or spaces between integers.
2. Click **Run with these inputs**. The header's **Run simulation** button uses the same values.
3. Wait for the fresh compiled RTL run to pass. The C, assembly, binary, hardware trace, output and recorded inputs then update together.
4. Use **Play**, **Go to**, or **Jump to output** to study the result.

For example, change addition's left input to `7` and right input to `8`. The compiled C contains those values, the ADD executes on the RTL, and the output becomes `15`.

The line **Inputs used in the displayed run** always describes the loaded capture. Editing fields does not change that line or the previous output. A notice tells you when the editor differs from the displayed run. Input drafts survive switching lessons within the open page; they are not saved across a page reload. **Restore lesson defaults** changes the editor; click Run to execute those defaults again.

## Editable fields

| Lesson | Inputs | Accepted values |
|---|---|---|
| Addition | Left and right number | Integers from 0 through 1,000,000 |
| Decisions | Two test numbers | Exactly two integers from -1,000,000 through 1,000,000 |
| Counting loop | Inclusive upper limit | 0 through 100; zero skips the loop |
| Array statistics | Five numbers | Exactly five signed integers in the same million-wide range |
| Recursive calls | Triangular-number input | 0 through 16; zero takes the base case |
| Sorting | Six numbers | Exactly six integers from 0 through 1,000,000; duplicates are allowed |
| Combined demo | Sixteen numbers, Fibonacci iterations, CRC message and repetitions | Sixteen signed integers in the same range; 0–50 iterations; 0–80 ASCII characters; 1–8 repetitions |

Tabs and line breaks are permitted in the CRC message. Its characters become ASCII bytes before CRC32 processing. Each field displays its bounds. Invalid input is explained and cannot start a simulation; the server independently checks the values too. The bounded sizes keep these study workloads inside the existing RAM, recursion and capture limits. Initialized zero values are placed in the firmware data image with `-fno-zero-initialized-in-bss`; the existing ban on uninitialized BSS remains in force.

Different data can change the control flow. Two positive decision inputs do not exercise the negative path; a zero loop limit has no loop-body execution. Checkpoints absent from the actual capture are listed as **Not visited with these inputs** instead of being invented. Clock counts and output labels follow the new run.

## How the run is produced

[The input module](../sim/cpu/program_inputs.py) defines field types, defaults, bounds and expected answers. It substitutes validated numeric and escaped string literals into a generated copy of the selected C lesson. The original lesson files remain default examples. The code pane shows the exact generated C used by the compiler, with matching debug-line attribution.

LLVM compiles that generated C; Icarus executes the resulting firmware on the core and RAM. The host computes expected answers from the submitted values and also uses those answers in the generated C exit checks. Every retired instruction, accepted write and trap is compared against the sequential ISA reference. Inputs, generated source identity, firmware identity and trace identity are recorded with the verified run.

Generated C and `inputs.json` accompany the active build under `build/cpu/visualizer/`. The latest successful run for each lesson, including `program.c` and `inputs.json`, is retained under `build/cpu/programs/<id>/`. A custom run replaces that lesson's saved run. Rebuilding the complete library with `python -B sim/cpu/build_programs.py` restores all seven default runs.

For command-line use, save an input object such as `{"left":7,"right":8}` to a JSON file, then run:

```powershell
python -B sim/cpu/build_visualizer.py --program add --inputs-json path/to/inputs.json
```

The JSON keys and bounds are defined by the input module. Omit `--inputs-json` to use lesson defaults. Reusing a capture requires identical inputs and matching source/artifact hashes. Python validation/oracle tests run with:

```powershell
python -B sim/cpu/test_program_inputs.py
```

The local HTTP endpoint accepts only typed input data for the seven built-in programs, using the existing origin and session-token checks. It does not accept arbitrary source code or command strings. When disconnected or opened as a standalone HTML file, recorded inputs stay visible and replay remains available; input editing and new simulations require the local server.
