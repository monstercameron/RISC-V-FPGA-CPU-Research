# SPDX-License-Identifier: MIT
# Requires RVA23 + Zfbfmin + Zvfbfmin + Zvfbfwma; probe support before dispatch.
.text
.option norvc
.option norelax

# Same arguments, layout and FP32 output boundary as gemv_bf16_rvv.
.globl gemv_bf16_native
.type gemv_bf16_native,@function
gemv_bf16_native:
    beqz a3, .Lnative_return
    csrrwi a7, frm, 0
    slli a5, a3, 1
.Lnative_rows:
    vsetvli t0, a3, e32, m2, ta, ma
    vmv.v.i v12, 0
    # Same VLMAX, same VL, double-width accumulator stays in v12:v13.
    vsetvli zero, t0, e16, m1, ta, ma
    mv t1, a0
    mv t2, a1
    mv t3, a4
    beqz t3, .Lnative_store
.Lnative_k:
    vle16.v v8, (t1)
    flh ft0, 0(t2)
    vfwmaccbf16.vf v12, ft0, v8
    add t1, t1, a5
    addi t2, t2, 2
    addi t3, t3, -1
    bnez t3, .Lnative_k
.Lnative_store:
    vse32.v v12, (a2)
    slli t1, t0, 1
    add a0, a0, t1
    slli t1, t0, 2
    add a2, a2, t1
    sub a3, a3, t0
    bnez a3, .Lnative_rows
    csrw frm, a7
.Lnative_return:
    ret
.size gemv_bf16_native, .-gemv_bf16_native

# uint16_t fp32_to_bf16_rne(float x): fa0 input, zero-extended a0 result bits.
.globl fp32_to_bf16_rne
.type fp32_to_bf16_rne,@function
fp32_to_bf16_rne:
    fcvt.bf16.s ft0, fa0, rne
    fmv.x.h a0, ft0
    slli a0, a0, 48
    srli a0, a0, 48
    ret
.size fp32_to_bf16_rne, .-fp32_to_bf16_rne
