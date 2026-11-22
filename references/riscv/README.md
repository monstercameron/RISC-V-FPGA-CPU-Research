# RISC-V specifications (unmodified upstream copies)

Byte-exact copies of official RISC-V International documents, retrieved 2026-11-22. They are third-party material under CC BY 4.0 (the MIT licence of this repository does not apply to them). The licence text is [licenses/RISCV-CC-BY-4.0.txt](../../licenses/RISCV-CC-BY-4.0.txt); hashes are also locked in [licenses/provenance.json](../../licenses/provenance.json) and checked by `scripts/check_repo.py`.

| File | Document and version | Source | SHA-256 | Size (bytes) | Licence |
|---|---|---|---|---|---|
| `riscv-isa-manual-3142f66-2026-11-21.pdf` | The RISC-V Instruction Set Manual, Volume I (Unprivileged ISA, including the V vector extension) and Volume II (Privileged Architecture), combined single document. Release `riscv-isa-release-3142f66-2026-11-21` (2026-11-21) | https://github.com/riscv/riscv-isa-manual/releases/download/riscv-isa-release-3142f66-2026-11-21/riscv-spec.pdf | `a836dee8d4d9a2a359df3b247a7c0c144ad020d41a37351661da80bf7e94ae4d` | 8921903 | CC BY 4.0 |
| `riscv-isa-manual-3142f66-2026-11-21.html` | Same release, HTML edition | https://github.com/riscv/riscv-isa-manual/releases/download/riscv-isa-release-3142f66-2026-11-21/riscv-spec.html | `7aab89d2cdbe96cb16fd55911487e7075c2e5ffe0fd815fefe1502cd392187d5` | 14570712 | CC BY 4.0 |
| `../rva23-profile-v1.0.pdf` | RVA23 / RVB23 profiles, ratified (release `rva23-rvb23-ratified`, 2025-01-21). Already in the repository; byte-identical to the release asset `rva23-profile.pdf`, so not duplicated here | https://github.com/riscv/riscv-profiles/releases/download/rva23-rvb23-ratified/rva23-profile.pdf | `af3519cdbfa1b3f12db6389b0bb9bcae171bf24fffd0dcf51d195ef49aaa9cfc` | 149681 | CC BY 4.0 |
| `riscv-sbi-v3.0.pdf` | RISC-V Supervisor Binary Interface Specification, v3.0 (release `v3.0`, 2025-07-16) | https://github.com/riscv-non-isa/riscv-sbi-doc/releases/download/v3.0/riscv-sbi.pdf | `2fc63fd1ab68d2df302c509763ed893fb5ed8a83523bac9246b98020d0c19cd9` | 737972 | CC BY 4.0 |

## Notes

- The ISA manual repository publishes a rolling release for each build of its main branch, tagged `riscv-isa-release-<commit>-<date>`. The tag above was the newest on 2026-11-22. It is not a numbered ratified edition, so cite the tag and commit `3142f66`, and compare against the ratified status of each extension in the document itself. The release also offers `riscv-spec.epub`, `norm-rules.html` and `norm-rules.json`, which are not copied here.
- No separate Debug specification was added.
- Licences were verified from each upstream repository's licence file (GitHub reports CC-BY-4.0 for riscv/riscv-isa-manual, riscv/riscv-profiles and riscv-non-isa/riscv-sbi-doc) and from the notice in the ISA manual HTML ("Creative Commons Attribution 4.0 International License").

## Attribution (CC BY 4.0)

The RISC-V Instruction Set Manual, the RVA23/RVB23 profiles and the RISC-V SBI specification are Copyright RISC-V International and the specification authors, licensed under the Creative Commons Attribution 4.0 International License (https://creativecommons.org/licenses/by/4.0/). The copies here are unmodified. RISC-V International does not endorse this project.
