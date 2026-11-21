# SPDX-License-Identifier: MIT
# Encoding specimens ONLY: do not call/fall through this mixed instruction list.
# Labels let verify_assembly.py extract independently checked 32-bit words.
.text
.option norvc
.option norelax
.globl opcode_examples
opcode_examples:
enc_lhu:       lhu t0, 0(a0)
enc_slli:      slli t0, t0, 16
enc_flw:       flw ft0, 0(a0)
enc_fsw:       fsw ft0, 0(a0)
enc_fadd:      fadd.s fa0, fa1, fa2, rne
enc_fmul:      fmul.s fa0, fa1, fa2, rne
enc_fmadd:     fmadd.s fa0, fa1, fa2, fa0, rne
enc_fdiv:      fdiv.s fa0, fa1, fa2, rne
enc_fsqrt:     fsqrt.s fa0, fa1, rne
enc_vsetvli:   vsetvli t0, a0, e32, m2, ta, ma
enc_vload:     vle16.v v8, (a0)
enc_vstore:    vse32.v v12, (a0)
enc_vfmacc:    vfmacc.vf v12, ft0, v10
enc_vfredosum: vfredosum.vs v8, v10, v12
enc_bf_narrow: fcvt.bf16.s fa0, fa1, rne
enc_bf_widen:  fcvt.s.bf16 fa0, fa1
enc_vbf_widen: vfwcvtbf16.f.f.v v10, v8
enc_vbf_narrow:vfncvtbf16.f.f.w v8, v10
enc_vbf_mac:   vfwmaccbf16.vf v12, ft0, v8
enc_fence:     fence iorw, iorw
enc_doorbell:  sw t0, 0x600(a0)
enc_prefetch:  prefetch.r 0(a0)
enc_cbo_clean: cbo.clean (a0)
