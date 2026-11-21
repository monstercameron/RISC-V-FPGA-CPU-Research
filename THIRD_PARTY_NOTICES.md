# Third-party notices

The root MIT license applies to original project contributions. It does not replace upstream terms on imported source, metadata, RTL or specifications. Preserve original copyright/license headers and attribution in copies and derivatives.

| Material and local scope | Upstream attribution and license |
|---|---|
| Transformers Python snapshots in `reference-sources/`, its archived copy under `llm-accelerator/planning-evidence/`, and `modeling_qwen3_5.py` copies under planning evidence / `notes/qwen3.8-27b/` | Hugging Face and the named contributors, including the Qwen Team as stated in file headers; [Apache-2.0 copy](licenses/TRANSFORMERS-APACHE-2.0.txt), [pinned upstream](https://github.com/huggingface/transformers/tree/1a55addd658aaa95b52871f5b72e91a6b91449b6) |
| Qwen configuration/index/tokenizer/generation/processor/chat-template snapshots and copied checkpoint metadata/headers | Copyright2026 Alibaba Cloud; [Apache-2.0 copy](licenses/QWEN-APACHE-2.0.txt), [pinned checkpoint license](https://huggingface.co/Qwen/Qwen3.8-27B/blob/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/LICENSE) |
| `sim/starter/vendor/picorv32.v` | Copyright2015-2021 Claire Xenia Wolf; [ISC COPYING](sim/starter/vendor/COPYING), [pinned upstream](https://github.com/YosysHQ/picorv32/tree/ef203c2b0a3fb793280f5114941416c425c5b461), [local source record](sim/starter/SOURCE.txt) |
| `sim/cpu/bench/vendor/dhrystone/` (Dhrystone benchmark, riscv-tests edition) | Copyright 2012-2015 The Regents of the University of California; [BSD-3-Clause](licenses/RISCV-TESTS-BSD-3-Clause.txt), [pinned upstream](https://github.com/riscv-software-src/riscv-tests/tree/3df703cd52d5f0d8224e3c50bf03c6cb70efff98/benchmarks/dhrystone), [local source record](sim/cpu/bench/vendor/dhrystone/SOURCE.txt). Dhrystone was written by Reinhold P. Weicker; C version 2.2 by Steven Pemberton. |
| `references/rva23-profile-v1.0.pdf` | RISC-V International and specification authors; [CC BY4.0 license](licenses/RISCV-CC-BY-4.0.txt), [official profiles repository](https://github.com/riscv/riscv-profiles). The bundled PDF is an unmodified reference specification; its attribution remains in the document. |

The source snapshot revisions and digests are in [reference-source-lock.json](reference-source-lock.json). License-file origins/digests are in [licenses/provenance.json](licenses/provenance.json). Imported source bytes and headers were preserved when adding repository housekeeping. Local analysis and comments about these sources do not confer ownership of the upstream work.

No model-weight payload, vendor FPGA tool, HardFloat implementation or vendor memory/PCIe IP is bundled by this setup. Proposed dependencies retain their own terms if introduced later. Referenced names and trademarks identify upstream projects; they do not imply endorsement.
