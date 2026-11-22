# RISC-V specifications (unmodified upstream copies)

Byte-exact copies of official RISC-V International documents, retrieved 2026-11-22. They are third-party material under CC BY 4.0 (the MIT licence of this repository does not apply to them). The licence text is [licenses/RISCV-CC-BY-4.0.txt](../../licenses/RISCV-CC-BY-4.0.txt); hashes are also locked in [licenses/provenance.json](../../licenses/provenance.json) and checked by `scripts/check_repo.py`.

| File | Document and version | Source | SHA-256 | Size (bytes) | Licence |
|---|---|---|---|---|---|
| `riscv-isa-manual-3142f66-2026-11-21.pdf` | The RISC-V Instruction Set Manual, Volume I (Unprivileged ISA, including the V vector extension) and Volume II (Privileged Architecture), combined single document. Release `riscv-isa-release-3142f66-2026-11-21` (2026-11-21) | https://github.com/riscv/riscv-isa-manual/releases/download/riscv-isa-release-3142f66-2026-11-21/riscv-spec.pdf | `a836dee8d4d9a2a359df3b247a7c0c144ad020d41a37351661da80bf7e94ae4d` | 8921903 | CC BY 4.0 |
| `riscv-isa-manual-3142f66-2026-11-21.html` | Same release, HTML edition | https://github.com/riscv/riscv-isa-manual/releases/download/riscv-isa-release-3142f66-2026-11-21/riscv-spec.html | `7aab89d2cdbe96cb16fd55911487e7075c2e5ffe0fd815fefe1502cd392187d5` | 14570712 | CC BY 4.0 |
| `../rva23-profile-v1.0.pdf` | RVA23 / RVB23 profiles, ratified (release `rva23-rvb23-ratified`, 2025-01-21). Already in the repository; byte-identical to the release asset `rva23-profile.pdf`, so not duplicated here | https://github.com/riscv/riscv-profiles/releases/download/rva23-rvb23-ratified/rva23-profile.pdf | `af3519cdbfa1b3f12db6389b0bb9bcae171bf24fffd0dcf51d195ef49aaa9cfc` | 149681 | CC BY 4.0 |
| `riscv-sbi-v3.0.pdf` | RISC-V Supervisor Binary Interface Specification, v3.0 (release `v3.0`, 2025-07-16) | https://github.com/riscv-non-isa/riscv-sbi-doc/releases/download/v3.0/riscv-sbi.pdf | `2fc63fd1ab68d2df302c509763ed893fb5ed8a83523bac9246b98020d0c19cd9` | 737972 | CC BY 4.0 |
| `extensions/riscv-elf-psabi-v1.0.pdf` | RISC-V ELF psABI, v1.0 (ratified release `v1.0`, 2022-11-08) | https://github.com/riscv-non-isa/riscv-elf-psabi-doc/releases/download/v1.0/riscv-abi.pdf | `a8d06bdcaa82a6a4567a1904dc27ef1ca1043ebaa1f523558c927a9d72bc23d9` | 273939 | CC BY 4.0 |
| `extensions/riscv-elf-psabi-draft-20261116-56561cb.pdf` | RISC-V ELF psABI, **draft** build 2026-11-16 (commit `56561cb`, pre-release `draft-20261116-56561cb...`; newer than v1.0, not a ratified edition) | https://github.com/riscv-non-isa/riscv-elf-psabi-doc/releases/download/draft-20261116-56561cb3e7330fe99a98fd27457229707b2786ae/riscv-abi.pdf | `a29ab77e963198ebceb9d2c30a6cf7f231a02078f6a38b22d31ac7f264eb1d8f` | 549256 | CC BY 4.0 |
| `extensions/riscv-plic-1.0.0.pdf` | RISC-V Platform-Level Interrupt Controller specification, 1.0.0 (ratified, 2023-03-12) | https://github.com/riscv/riscv-plic-spec/releases/download/1.0.0/riscv-plic-1.0.0.pdf | `82644c7701601baad8abe8b8c194a6aa89d0c1c26029f590f20818e319ccb21a` | 545211 | CC BY 4.0 |
| `extensions/riscv-aclint-1.0-rc4.pdf` | RISC-V ACLINT specification, v1.0-rc4 (release candidate, 2022-01-14; **not ratified**; repository now archived as riscvarchive/riscv-aclint) | https://github.com/riscv/riscv-aclint/releases/download/v1.0-rc4/riscv-aclint-1.0-rc4.pdf | `fb7f1473470fbc2a2155f0ae365a4e94f95d0451ca207a7d45671a7be6b76375` | 133041 | CC BY 4.0 |
| `extensions/riscv-debug-1.0.pdf` | RISC-V Debug Specification 1.0 (ratified, release `1.0`, 2025-02-21; asset `riscv-debug-specification.pdf`) | https://github.com/riscv/riscv-debug-spec/releases/download/1.0/riscv-debug-specification.pdf | `ce2787b25233a6109c9bc767b2bc497798148b721390f72fb9b48ff0ed986fc8` | 2495279 | CC BY 4.0 |
| `extensions/rvv-intrinsic-v1.0-ratified.pdf` | RISC-V Vector Extension Intrinsic Document, v1.0 (ratified, release `v1.0-ratified`, 2025-04-25; asset `v-intrinsic-spec.pdf`) | https://github.com/riscv-non-isa/rvv-intrinsic-doc/releases/download/v1.0-ratified/v-intrinsic-spec.pdf | `148f31560335620da20330727a35184e90cfed635d32ef0055511995dc0c9c07` | 8217551 | CC BY 4.0 (document); the repository's BSD-3-Clause applies to its code files only |
| `extensions/riscv-dot-product-v0.0.1-draft.pdf` | Vector Dot-Product Extension (Zvqdotq), v0.0.1 **DRAFT, not ratified** (release `v0.0.1`, 2024-12-06). Zvqdotq is the extension the project calls Zvdot4a8i | https://github.com/riscv/riscv-dot-product/releases/download/v0.0.1/dot-product.pdf | `d4cc2e9b020764443009a3c6bb9267ee4bb9704248e8c100c6c05561f60b34a2` | 198634 | CC BY 4.0 |

## Extension index (status, and where the specification is)

Status: in use = implemented or exercised in this repository now; building = Linux milestone work; planned = on the roadmap. "Manual" means the ISA manual copy above (release 3142f66, 2026-11-21), which now contains these extensions; no separate copy was added. Section numbers are from the manual's table of contents (Vol. I = unprivileged, Vol. II = privileged). Ratification status is stated by the manual itself; where a row says ratified it is the project's reading and should be checked in the extension's own section.

| Extension | Project status | Where the spec is | Version / state |
|---|---|---|---|
| RV64I, M | in use | Manual Vol. I, ch. 2 (base) and M extension chapter | ratified |
| Zba, Zbb, Zbs (B) | in use | Manual Vol. I, ch. 8 (8.1-8.3) | ratified |
| Zicsr, Zifencei, Zicntr | in use | Manual Vol. I, 4.1-4.3 | ratified |
| F, D | in use | Manual Vol. I, ch. 6 | ratified |
| V (Zve*, base vector architecture) | in use (subset) | Manual Vol. I, ch. 9 (9.1-9.7); see also `cpu/RVV-CONTRACT.md` | ratified |
| RVV C intrinsics | in use for kernels | `extensions/rvv-intrinsic-v1.0-ratified.pdf` | v1.0 ratified (newer draft builds exist upstream, not copied) |
| A (Zaamo/Zalrsc), Zawrs, Zacas | building / planned | Manual Vol. I, ch. 5 (Zawrs 5.5, Zacas 5.9) | ratified |
| C (Zca, Zcb, Zcmop) | building / planned | Manual Vol. I, ch. 7 | ratified |
| M/S/U privilege, Sv39, Svade, Svpbmt, Svnapot, Svinval, Sstc, Ssstateen/Smstateen, Sscofpmf, Ssnpm | building / planned | Manual Vol. II, ch. 3-9 (Sm ch. 6, Sv ch. 7, Ss ch. 8) | ratified (as stated in each section) |
| RVA23U64 / RVA23S64 / RVB23 profiles | target | `../rva23-profile-v1.0.pdf`; the manual build also has profile chapters (RVA23 and RVB23) | ratified (release 2025-01-21) |
| SBI | building | `riscv-sbi-v3.0.pdf` | v3.0 ratified |
| PLIC | building | `extensions/riscv-plic-1.0.0.pdf` | 1.0.0 ratified |
| CLINT / ACLINT timer | building | `extensions/riscv-aclint-1.0-rc4.pdf`. The CLINT itself is a de-facto SiFive interface with no official RISC-V specification found | ACLINT v1.0-rc4, not ratified |
| Debug (and trace) | optional | `extensions/riscv-debug-1.0.pdf` | 1.0 ratified |
| ELF psABI | in use (toolchains) | `extensions/riscv-elf-psabi-v1.0.pdf`; newer `extensions/riscv-elf-psabi-draft-20261116-56561cb.pdf` | v1.0 ratified; the draft is not a ratified edition |
| Zicond | planned | Manual Vol. I, 4.7 | ratified |
| Zimop, Zcmop | planned | Manual Vol. I, 4.16 and 7.10 | ratified |
| Zihintntl, Zihintpause | planned | Manual Vol. I, 4.18 and 4.19 | ratified |
| Zicbom / Zicboz / Zicbop (CMO) | planned | Manual Vol. I, ch. 4 (Zicbom, Zicboz and Zicbop sections) | ratified |
| Zfa | planned | Manual Vol. I, 6.6 | ratified |
| Zfh, Zfhmin | planned | Manual Vol. I, 6.4 and 6.5 | ratified |
| Zvfh, Zvfhmin | planned | Manual Vol. I, 9.9 and 9.8 | ratified |
| BF16: Zfbfmin, Zvfbfmin, Zvfbfwma | planned | Manual Vol. I, 6.7, 9.10 and 9.11 | ratified; the separate riscv/riscv-bfloat16 v1.0 release is superseded by the manual and not copied |
| Zvbb, Zvbc | planned | Manual Vol. I, 9.12 and 9.13 | ratified |
| Vector crypto Zvk*, Zkt, Zvkt | planned | Manual Vol. I, ch. 11 (Zkt 11.2, vector crypto 11.3) | ratified; the separate riscv/riscv-crypto v1.0.0 release is superseded by the manual and not copied |
| Zvqdotq (project name Zvdot4a8i) | planned | `extensions/riscv-dot-product-v0.0.1-draft.pdf` | **DRAFT, not ratified**, v0.0.1, 2024-12-06. The name Zvdot4a8i appears neither in the manual nor in the official draft |
| Matrix extensions (IME, VME, AME) | planned research | Manual Vol. I, ch. 12 is only a placeholder. No official release or tagged PDF was found: the Integrated Matrix Extension task group has only the administrative repository `riscv-admin/integrated-matrix-extension`, and `riscv/riscv-matrix` does not exist | **DRAFT / not available**; nothing copied |
| Packed SIMD (P) | not used | Manual Vol. I, ch. 10 | not used |

Not copied (not requested or not needed): AIA (`riscv/riscv-aia`, release 20250312), IOMMU (`riscv-non-isa/riscv-iommu`, release 20260222), newer RVV intrinsic draft builds. Fetch them from the upstream repositories if the project starts depending on them.

## Licence notes for the extension files

Each upstream repository was checked on 2026-11-22. riscv-elf-psabi-doc, riscv-plic-spec, riscv-dot-product and rvv-intrinsic-doc (`COPYING.CC`) carry the CC BY 4.0 legal code; riscv-debug-spec and riscv-aclint state CC BY 4.0 (the debug repository notes some files may also be under another licence stated in that file). The existing [licenses/RISCV-CC-BY-4.0.txt](../../licenses/RISCV-CC-BY-4.0.txt) is the same CC BY 4.0 text, so no new licence file was needed. The RVV intrinsic repository's BSD-3-Clause (`COPYING.BSD`) covers code files in that repository, not the PDF. The PLIC specification states it is a derivative of the RISC-V Instruction Set Manual Volume II.

## Notes

- The ISA manual repository publishes a rolling release for each build of its main branch, tagged `riscv-isa-release-<commit>-<date>`. The tag above was the newest on 2026-11-22. It is not a numbered ratified edition, so cite the tag and commit `3142f66`, and compare against the ratified status of each extension in the document itself. The release also offers `riscv-spec.epub`, `norm-rules.html` and `norm-rules.json`, which are not copied here.
- The files in `extensions/` were added on 2026-11-22 (about 12.4 MB in total, largest 8.2 MB) from official release assets only, byte-exact.
- Licences were verified from each upstream repository's licence file (GitHub reports CC-BY-4.0 for riscv/riscv-isa-manual, riscv/riscv-profiles and riscv-non-isa/riscv-sbi-doc) and from the notice in the ISA manual HTML ("Creative Commons Attribution 4.0 International License").

## Attribution (CC BY 4.0)

The RISC-V Instruction Set Manual, the RVA23/RVB23 profiles, and the SBI, ELF psABI, PLIC, ACLINT, Debug, RVV intrinsic and Vector Dot-Product specifications are Copyright RISC-V International and the specification authors, licensed under the Creative Commons Attribution 4.0 International License (https://creativecommons.org/licenses/by/4.0/). The copies here are unmodified. RISC-V International does not endorse this project.
