# FPGA resource estimate and development-board choice

**Current normative refinement:** [implementation contract](implementation-contract.md) and [ABI 1](abi-v1.md). The [review record](refinement-review.md) tracks independent findings; [checks](refinement-checks.json) are planning evidence, not RTL or hardware qualification.

Research date: October 23, 2026. Scope: the complete shared-engine Qwen3.8-27B text/vision accelerator in `plan.md` and `memory-plan.md`. Prices are USD listing snapshots, with shipping as displayed; destination, tax, import charges, stock and condition require checking at purchase. The original under-$500 budget remains the shopping constraint.

**Recommendation:** target an **XCKU5P**, preferably the documented **RK-XCKU5P-F V1.2** board with 2 GiB DDR4 and onboard JTAG/UART. An observed candidate listing is $246.42 + $45 shipping, about $291 before tax. Match the PCB revision to the documentation before ordering. Budget **roughly 40–90k physical LUT6, 25–80 DSP slices and 70–170 RAMB36 equivalents** for an initial eight-lane core plus one DDR and one PCIe DMA subsystem. This is a pre-synthesis engineering envelope, not a measured utilization result.

The cheapest large-fabric candidate found is a used XC7K325T board at about $69 including displayed shipping. Its memory, exact board identity and usable design collateral remain unverified, so it is an experimental bargain rather than the default development recommendation. The lower purchase price could be outweighed by board bring-up work. [KU5P candidate listing](https://www.ebay.com/itm/236824729046), [K325T listing](https://www.ebay.com/itm/298386101242).

## 1. What determines the LUT count

The model's 27B parameters are stored in external memory. The controller applies different weights while reusing the same matrix, vector, attention, state and nonlinear hardware. Therefore LUT count scales primarily with arithmetic lane count, precision, pipeline depth, memory ports, buffering and transport complexity. It does not scale as one LUT or one multiplier per parameter, nor as 64 physical copies of a decoder layer.

The intended full graph still needs all its operators: FP32 recurrence/reductions, BF16 casts, both attention types, normalization, convolution, RoPE, nonlinear functions, patch/position/merger operations and logits. Sharing saves hardware by taking more cycles. Omitting an operator or doing it on the host would change the objective.

There are three separate numbers to track:

- **Accelerator core:** arithmetic, sequencer, tensor DMA, local banks and operator controllers.
- **Board infrastructure:** DDR controller/PHY, PCIe/DMA, reset/clock logic and host-access interfaces.
- **Development build:** counters, trace buffers and debug logic, plus free resources for changes and timing closure.

All LUT figures below are physical AMD six-input LUT counts. Marketing logic cells, Intel ALMs/LEs and Lattice four-input LUTs are not interchangeable counts. The Arty A7-100T, for example, has 63,400 LUT6; “100T” does not mean 100,000 LUT6.

## 2. Published implementation anchors and their limits

AMD's published floating-point resource table gives the following isolated Kintex-7 implementations. These are useful order-of-magnitude checks, **not measurements of our selected HardFloat wrappers**:

| Published FP32 operation | LUTs | Flip-flops | DSPs |
|---|---:|---:|---:|
| Fused multiply-add | 706 | 1,092 | 2 |
| Iterative divider | 195 | 199 | 0 |
| Exponential | 809 | 620 | 1 |
| Logarithm | 740 | 1,124 | 4 |

The divider example accepts a new operation only every 26 cycles. The FMA entry's isolated timing is not whole-core timing. Our open RTL may handle subnormals, exceptions, backpressure, conversion, pipeline placement and DSP inference differently; qualify its arithmetic rather than substituting vendor results. [AMD floating-point implementation results, Vivado 2025.1](https://download.amd.com/docnav/documents/ip_attachments/floating-point.html).

Memory infrastructure is substantial. AMD's 2026.1 DDR4 table lists an UltraScale+ 32-bit complete-controller example (`SN96`, XCKU11P, non-AXI) at **9,029 LUTs, 11,247 FFs and three DSPs**. An AXI wrapper, calibration choice and a different PHY can change this. [AMD DDR4 implementation results](https://download.amd.com/docnav/documents/ip_attachments/ddr4.html).

An UltraScale+ PCIe Gen3 x4, one-channel memory-mapped DMA example (`xcvu3p-dma-g3x4_chnl1_mm`) uses **14,351 LUTs and 18,859 FFs**. This demonstrates why a hardened PCIe endpoint does not make its entire DMA subsystem free in fabric. A leaner LitePCIe design can differ; do not add XDMA and LitePCIe as though both are required. [AMD PCIe DMA implementation results](https://download.amd.com/docnav/documents/ip_attachments/xdma.html).

These anchors justify reserving tens of thousands of LUTs for the integrated system. They do not establish our target clock or resource fit. No synthesis or place-and-route of the complete accelerator has been performed.

The later [plan gap audit](plan-gap-audit.md) makes arithmetic qualification a purchase/fit gate: the chosen HardFloat FMA interface is combinational, so external wrapper registers do not by themselves establish an internally pipelined 100/200-MHz unit. Measure actual feedback latency, initiation interval and DSP inference. The candidate eight-lane schedule uses 16 independent output rows per lane (512 bytes of FP32 accumulator state) and two 8-KiB packed weight tiles. Their payload fits the planning allowances, but banking, pipeline registers and routing still need synthesis; the 40–90k estimate remains conditional.

## 3. Bottom-up eight-lane budget

Assumptions: eight reusable FP32 FMA-capable lanes; BF16 external weight/activation storage with explicit conversions; shared divider/square-root and nonlinear machinery; 64–128 KiB logical local scratch; external tensor/state storage; one DDR channel and one PCIe DMA path. Start at 100 MHz for integration; 150–200 MHz is an optimization target requiring timing closure. Counters and modest debug are included.

| Planned block | Low LUT6 allowance | High LUT6 allowance | Reason for uncertainty |
|---|---:|---:|---|
| Sequencer, descriptors, shape checks, 64-bit addresses | 3,000 | 6,000 | Descriptor complexity and address datapaths |
| Attention/Delta/FFN/vision controllers | 3,000 | 6,000 | Shared scheduling versus replicated pipelines |
| Vector/norm/reduction control | 2,000 | 5,000 | Trees, masks and accumulator handling |
| Shared divide/sqrt/conversion support | 1,000 | 3,000 | Iterative arithmetic and exception behavior |
| Shared nonlinear functions and range reduction | 2,000 | 6,000 | Approximation degree, precision and ROM design |
| Tensor DMA, scratch routing, queues and credits | 5,000 | 10,000 | Bus widths, outstanding transactions and bank arbitration |
| Debug and counters | 1,000 | 3,000 | Probe width and capture controls |
| Reset/clock control logic | 1,000 | 1,000 | Working allowance; dedicated clock primitives counted separately |
| Eight FP32 lanes, including lane-local control | 8,000 | 16,000 | 1–2k per lane is an allowance above the isolated vendor FMA anchor |
| **Accelerator subtotal** | **26,000** | **56,000** | Before board DDR/PCIe |
| One DDR controller/PHY and integration | 8,000 | 16,000 | Memory width, vendor/LiteDRAM choice, wrappers |
| One PCIe endpoint/DMA integration | 7,000 | 16,000 | Lean implementation through fuller DMA configuration |
| **Integrated development total** | **41,000** | **88,000** | Round to **40–90k** for planning |

These ranges are explicit engineering assumptions, not statistical confidence intervals. Their precision is for reproducible summation, not a claim that the design will use exactly 41,000 LUTs. Shared numerical functions reuse arithmetic; the table does not instantiate a separate eight-lane engine for every mathematical operation. If the first RTL fails to infer DSPs or BRAM, the estimate may be exceeded significantly.

The corresponding eight-lane DSP allowance is 27–72: 16–32 for lanes, 8–32 shared arithmetic and 3–8 for memory-side implementation. Rounding to 25–80 is appropriate at this stage. Reserve roughly 50–125k flip-flops for the integrated pipelines/interfaces as a separate unmeasured allowance. Inspect actual LUTRAM, carry-chain, FF, clock, I/O and transceiver counts in reports; low LUT occupancy alone cannot establish fit.

Use approximately **65% LUT occupancy as an initial project target**, leaving room for debug, pipelining, routing and changes. This is our planning margin, not a vendor rule. A design can route above it, or fail below it because of local congestion or constrained I/O.

## 4. Memory blocks and growth with parallelism

64 KiB of payload is at least 15 RAMB36 blocks by raw bit capacity. A conventional 32/64-bit payload organization generally needs at least 16 because parity bits are not automatically useful payload. Banking and shallow buffers can increase the count. Never synthesize large tensor arrays into registers accidentally, and do not reset every memory bit through fabric logic.

| Eight-lane subsystem | RAMB36-equivalent allowance |
|---|---:|
| 64–128 KiB scratch, including the tile buffers already budgeted in the memory plan | 24–48 |
| Nonlinear tables/constants | 4–12 |
| Additional transport/CDC queues outside that scratch budget | 8–20 |
| DDR controller/PHY | 24–32 |
| PCIe DMA queues | 8–40 |
| Debug capture | 4–16 |
| **Total** | **72–168** |

The extra transport queues are explicitly additional storage, not a second charge for the 16-KiB scratch DMA tiles. Some implementations map queues to UltraRAM or LUTRAM; compare the same total payload and port requirements before treating that as a saving. BRAM36 means a 36-Kibit block; UltraRAM288 is a different, larger, less flexible storage primitive. A 512-KiB scratch profile needs about 128 RAMB36 blocks in a simple data organization before ROMs/controllers/debug, or an appropriate BRAM/UltraRAM mix.

The following envelopes come from `fpga_resource_estimate.py`. At 32/64 lanes it adds a further 25% of accelerator LUTs for wider routing, fanout and control; this is a design allowance. The memory-block budget must also be recomputed for those wider profiles.

| FP32 lanes | Accelerator alone, LUT6 | With one DDR + PCIe DMA, LUT6 | DSP allowance | Dense-only compute floor at 200 MHz |
|---|---:|---:|---:|---:|
| 1 | 19–42k | 34–74k | 13–44 | 128.11 s/token |
| 8 | 26–56k | 41–88k | 27–72 | 16.01 s/token |
| 32 | 50–104k before wider-routing allowance | 77.5–162k | 75–168 | 4.00 s/token |
| 64 | 82–168k before wider-routing allowance | 117.5–242k | 139–296 | 2.00 s/token |

The dense compute floors use the previously audited 25,621,954,560 MACs/token and assume one accepted MAC/lane/cycle. They omit attention, Delta work, nonlinear functions, memory and pipeline stalls. A pipelined FMA needs interleaved independent accumulators to avoid feedback hazards; its latency is not automatically an initiation interval of one for one dependent dot product. At 100 MHz these floors double. These values are arithmetic limits, not predicted achieved token rates.

Increasing lane count will help prefill when weights are reused across rows. For single-sequence host-streamed BF16 decode, the host link can become the limit long before all FPGA DSPs are used. Therefore an eight-lane initial target is a reasonable development choice; committing to 64 lanes before measuring the memory path is premature.

## 5. FPGA devices that fit the development envelope

| FPGA | Physical LUT6 | FFs | DSPs | RAMB36 blocks | UltraRAM288 blocks | 41–88k LUT budget as device fraction |
|---|---:|---:|---:|---:|---:|---:|
| XC7A100T | 63,400 | 126,800 | 240 | 135 | 0 | 65–139% |
| XC7A200T | 134,600 | 269,200 | 740 | 365 | 0 | 30–65% |
| XC7K325T | 203,800 | 407,600 | 840 | 445 | 0 | 20–43% |
| XCKU3P | 162,720 | 325,440 | 1,368 | 360 | 48 | 25–54% |
| XCKU5P | 216,960 | 433,920 | 1,824 | 480 | 64 | 19–41% |

Resource counts are device capacities, not resources necessarily available after a prebuilt platform shell. Package and board routing determine which hard interfaces and memory connections can be used. [AMD 7-series selection guide](https://docs.amd.com/v/u/en-US/7-series-product-selection-guide), [AMD UltraScale/UltraScale+ DS890](https://docs.amd.com/v/u/en-US/ds890-ultrascale-overview).

K325T, KU3P and KU5P leave comfortable planning room for the initial design. A200T is also plausible, with less margin. A100T does not cover the integrated eight-lane high estimate and may also run out of BRAM; it is a board for reduced configurations and early operators. KU5P is the strongest balanced target here because its DSP, LUT and UltraRAM resources also permit larger prefill scratch and later experiments.

## 6. Boards and cost to start development

| Candidate | Observed board + displayed shipping | RAM and host connection | Assessment for this project |
|---|---|---|---|
| **Documented RK-XCKU5P-F V1.2** | Candidate [listing](https://www.ebay.com/itm/236824729046): **$246.42 + $45 = $291.42**, seller lists new | Matching documented revision: 2 GiB DDR4, 32-bit; PCIe Gen3 x4; onboard JTAG/UART | **Best overall development target** if the delivered board/revision matches the collateral |
| **Used generic XC7K325T board** | [Listing](https://www.ebay.com/itm/298386101242): **$65.79 + $3 = $68.79** | Exact memory, PCIe wiring, programming setup and constraints not verified | **Cheapest large fabric found**; choose only if board bring-up/reverse engineering is acceptable |
| **Alibaba AS02MC04 / KU3P** | [Listing](https://www.ebay.com/itm/406548987181): **$197.65 + $20 = $217.65**, used | PCIe Gen3 x8; no external DDR interface in the inspected LiteX platform/target; budget as host-backed | Good PCIe/streaming platform, weaker for local native-layer/state experiments |
| **Arty A7-100T** | [Manufacturer](https://digilent.com/shop/arty-a7-100t-artix-7-fpga-development-board/): **$322** before shipping | 256 MB DDR3L; USB JTAG/UART; 10/100 Ethernet; no PCIe connector | **Easiest conventional lab bring-up**, but poor value for the full eight-lane LLM design |
| **SQRL Acorn CLE-215+ / A200T** | No suitable currently available, tested unit confirmed in this research pass | Documented 1 GiB DDR3, PCIe Gen2 x4 M.2; needs suitable carrier/programming/cooling | Useful opportunistic alternative, not a confirmed current buy |

The $55 Acorn result found was **sold and “for parts or not working”**; it is excluded as a working-board offer. Old wiki prices are not current stock. [Excluded listing](https://www.ebay.com/itm/307044718786), [Acorn bring-up documentation](https://github.com/enjoy-digital/litex/wiki/Use-LiteX-on-the-Acorn-CLE-215/1dbeb59b35d1284f54e8a25f0ac76ce3f1be3284).

Budget **$320–400 before tax for the board/accessory portion** of the KU5P candidate, allowing for power supply, cables, cooling or an adapter if not included. This is an allowance, not a quoted bundle. Compatible host access is unverified; include any host, RAM and storage acquisition separately before an all-in decision. A desktop with an electrically suitable PCIe slot is much easier than a laptop for transport work. An ordinary USB connection or passive USB-C adapter does not establish PCIe access.

For the cheap K325T, a provisional **$100–180 before tax** allows for a programmer, power and cooling, but cannot price missing schematics, repairs or an undocumented memory interface. Spending $69 on the card is not evidence of a $69 development system. For the KU3P, allow roughly **$250–330** with a JTAG solution and cooling/power needs; external DRAM cannot simply be added through software if it is absent from the board.

The Arty offers onboard programming, documented DDR3L and conventional vendor examples. Its official memory link is 16-bit at 667 MT/s, about 1.334 GB/s raw; its 100-Mbit Ethernet ceiling is 12.5 MB/s before protocol overhead. That is unsuitable for repeatedly supplying a 51-GB/token weight stream. It remains reasonable if already owned or if the immediate goal is reduced-size operator development. [Digilent specifications](https://digilent.com/shop/arty-a7-100t-artix-7-fpga-development-board/).

## 7. Why the exact KU5P board revision matters

The published RK-XCKU5P-F V1.2 collateral identifies a -2 speed-grade chip, 32-bit 2-GiB DDR4, onboard FT2232HQ JTAG/UART, and **PCIe Gen3 x4**. Use those documented interfaces for planning; the candidate marketplace title says x8 and is inconsistent. The photo/PCB marking, RAM chips and schematic must match before treating the listing as that board. [Board collateral](https://github.com/tommythorn/rk-xcku5p-f-v1.2).

The current LiteX platform declares 32 DDR data pins and a `pcie_x4` interface. Its target instantiates a DDR4 PHY and a one-DMA Gen3 x4 interface, defaults the system clock to 100 MHz, and **maps only 1 GiB of the physically described 2 GiB** in its default configuration. Using all memory requires checking the address map/controller configuration and memory testing. A target file's existence is evidence of integration work, not a guarantee that a purchased board will pass DDR calibration or sustained DMA. [Platform definition](https://raw.githubusercontent.com/litex-hub/litex-boards/master/litex_boards/platforms/aliexpress_rk_xcku5p.py), [target implementation](https://raw.githubusercontent.com/litex-hub/litex-boards/master/litex_boards/targets/aliexpress_rk_xcku5p.py).

For the KU3P alternative, open board resources and a LiteX target reduce the unknowns around clocks/JTAG/PCIe. The inspected platform does not define an external DDR bus, so the plan must place large state in host memory. This is a material difference from the KU5P development board, even though both chips contain useful on-chip RAM. [AS02MC04 platform](https://raw.githubusercontent.com/litex-hub/litex-boards/master/litex_boards/platforms/alibaba_xcku3p.py), [AS02MC04 target](https://raw.githubusercontent.com/litex-hub/litex-boards/master/litex_boards/targets/alibaba_xcku3p.py).

## 8. What these boards can execute versus what they can store

The architecture can theoretically execute the entire graph using streamed external weights. The KU5P's 2 GiB DDR4 is useful for real-size block tests, the 144-MiB FP32 Delta state, short-context KV and tile staging. At 4K context the model's BF16 KV is 256 MiB; together with Delta and conv state, that is about 404 MiB before scratch. A native BF16 decoder block is roughly 710–731 MiB of projection/FFN matrices, so one-block development is useful on this board. The untied LM head alone is about 2.37 GiB and already requires tiling on 2 GiB.

Complete active model weights are 54.71 GB BF16. The memory plan's hypothetical W4 text plus BF16 vision profile still needs about 14.79 GB before persistent state and workspace. None of these small-DDR candidates stores the complete model locally. Even at W4, model quality remains an open gate. At 32K context, KV alone reaches 2 GiB, leaving no local room for other state on a 2-GiB board.

PCIe bandwidth constrains host streaming. Encoding-only upper bounds before transaction overhead are approximately 3.94 GB/s for Gen3 x4, 7.88 GB/s for Gen3 x8 and 2.00 GB/s for Gen2 x4. These are derived from lane rate and encoding, not measured DMA. At an illustrative **3 GB/s effective host link**, 51.25 GB of BF16 weight reads alone take **17.08 seconds/token**; the hypothetical 13.22-GB W4 weight stream takes 4.41 seconds. Staging through DDR, state transfers and computation add constraints. Native 27B inference should therefore be treated as a functional/architecture experiment on these boards, not a promised interactive deployment.

An eight-lane BF16-source FMA array at 200 MHz requires 3.2 GB/s of weights if each weight is used once. This is already close to a Gen3 x4 link's practical range; at 100 MHz it requires 1.6 GB/s. Wider arrays become more useful for prefill/batching and resident kernels than for single-sequence streamed decode. Keep the memory plan's per-tier accounting when choosing lane count.

Larger-memory cards are a future phase. A used U200 can provide 64-GB-class DDR, but the indexed U200 auction found ended October 18 at $1,007; it is historical pricing, not a current offer under $500. Alveo tool licensing also needs checking independently. [Ended U200 auction](https://www.ebay.com/itm/198712656910). This research does not establish an available sub-$500 card that combines complete BF16 model residency, a verified free implementation flow and supported board infrastructure.

## 9. Free toolchain and hidden development costs

Use Icarus/Verilator and Python for simulation/reference work, then Vivado for the target FPGA's synthesis, implementation and programming. The selected vendor implementation tool is free of charge for the relevant supported devices; it is not an entirely open-source place-and-route flow. HardFloat and our SystemVerilog arithmetic remain the initial free RTL path. LiteDRAM/LitePCIe are possible board infrastructure, with their own versions and license notices pinned.

AMD's 2026.1 device table lists **all 7-series devices**, plus **XCKU3P and XCKU5P**, in BASIC. It does **not** include XCKU040 in BASIC, so a cheap KCU105 is not automatically a zero-tool-cost alternative. Alveo has a dedicated tier. Use the exact part number and release rather than assuming every Kintex device has identical entitlement. [Official device/tier table](https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Device-Availability-by-Subscription-Tier).

BASIC requires a free license file and annual renewal. AMD's Alveo FAQ describes a one-year license associated with card purchases; do not assume a used card brings an unused or transferable entitlement. Confirm any extra IP/debug features against the selected tier, and preserve counters/trace-based debug. [AMD licensing FAQ](https://www.amd.com/en/products/software/adaptive-socs-and-fpgas/licensing-faq.html), [feature matrix](https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Feature-Availability-by-Subscription-Tier).

The 2026.1 BASIC feature matrix limits XSIM to 50K instances and ILA to five probes with a maximum width of 1,024 bits; some debug insertion features are unavailable. Keep large functional simulations in the existing free Icarus/Verilator path and plan compact hardware probes plus explicit status/trace registers. Device support alone does not imply every edition feature is unrestricted. [AMD feature matrix](https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Feature-Availability-by-Subscription-Tier).

The actual workstation is a Snapdragon X2 Elite Extreme **ARM** machine. AMD Vivado2026.1 specifies an x86-64 host; native Windows programming on this machine is not established. Existing Ubuntu-24.04 aarch64 WSL has Icarus/Python for the free start. A supported x86-64 build/programming host and suitable native Linux PCIe runtime host must be confirmed; one compatible Linux desktop could serve both. The inspected LitePCIe example generates a Linux driver. WSL, x86 emulation or a USB programmer does not prove host-driver/slot compatibility. [AMD supported hosts](https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Supported-Operating-Systems).

Measured physical RAM is 47.61GiB; current free C: disk snapshot is 45.22GiB. A 55.56GB original checkpoint does not fit that disk, and original+packed copies need >110GB before reserve. The implementation contract requires at least155GB free for that full-copy strategy, measured RAM limits/30% margin, and bounded tensor jobs now. Recheck space before jobs. Board prices exclude a possibly needed host/storage, shipping/tax, adapters, power and cooling; all-in budget remains unresolved until actual host access is verified.

## 10. Turn this estimate into an actual utilization report

Before buying primarily on the resource envelope, synthesize a small set of real modules for both **XC7K325T** and **XCKU5P** with the actual arithmetic configuration. This does not require owning either FPGA. This document recommends that experiment; it has not been run here.

1. Synthesize one FP32 FMA/add/multiply/divide/sqrt wrapper and the nonlinear approximation pipeline, with subnormal/rounding policy and backpressure fixed. Verify DSP inference, pipeline latency and numerical behavior.
2. Synthesize 1/8/32-lane tiled GEMV using real SRAM wrappers, then grouped attention and one 128x16 Delta panel pipeline. Constrain clock and preserve useful outputs so logic is not optimized away.
3. Synthesize the exact chosen DDR and PCIe example separately; record LUT/FF/DSP/BRAM/URAM/clock/I/O use and licensing. Avoid counting shared interconnect twice.
4. Integrate one complete tiny text/vision graph with all controllers, not only a MAC benchmark. Produce hierarchical utilization, timing, inferred-memory and power reports.
5. Route the complete development configuration at 100 MHz first, then attempt 150/200 MHz. Inspect worst negative slack, congestion, CDC, RAM ports and debug growth; record physical timing separately from out-of-context synthesis.
6. Apply the M0-M6 memory gates and D0-D9 functional gates already in the plan. On hardware, establish DDR calibration/memtest and sustained bidirectional DMA before running numerical workloads.

Report the full part/package/speed grade, tool/IP versions, HDL revision, lane counts, precisions, scratch size, enabled interfaces, clock constraints and debug configuration with each result. Replace the estimated ranges only with those reproducible reports. Do not mistake successful synthesis for routing success, or numerical simulation for a memory bandwidth measurement.

Conditional on supported host access and the documented board gates, the current candidate is **XCKU5P / documented RK board as the primary development target; XC7K325T as the lowest-price experimental alternative**. Preserve the free simulated start, build eight lanes first, and prioritize the memory interface before increasing parallelism. Both can have ample logic for a shared complete-graph engine; neither has been demonstrated to run this model end-to-end yet.

Reproducible budget: `python fpga_resource_estimate.py --out fpga-resource-estimate.json`. The script records every allowance, sums the profiles, checks device fractions and derives encoding-rate ceilings. It does not run synthesis or claim access to a board.

The [gap audit](plan-gap-audit.md) adds the remaining development gates: exact PCB/XDC and tested DDR extent, registered host DMA mapping and ABI, bounded workloads/output allocation, safe cancel/reset, clock-domain and reset analysis, post-route timing, and sustained power/thermal/memory-integrity testing. Its revised topology example shows why 3-GB/s host supply plus 4-GB/s shared DDR staging yields a 25.876-s/token DDR floor even when dense compute alone suggests 16.014 s. Native-model RTL simulator wall time must also be measured before full checkpoint runs.
