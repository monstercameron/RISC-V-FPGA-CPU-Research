# SPDX-License-Identifier: MIT
# RV64 LP64D callable teaching kernels; see README.md for bounds and status.
.text
.option norvc
.option norelax

# float dot_bf16_fma(const uint16_t *x, const uint16_t *w, size_t n)
# a0=x, a1=w, a2=n, fa0=result. Increasing k, +0 initial accumulator.
# Widening here is a bit operation; exceptional-value policy is caller-owned.
.globl dot_bf16_fma
.type dot_bf16_fma,@function
dot_bf16_fma:
    fmv.w.x fa0, zero
    beqz a2, .Lbf_done
.Lbf_loop:
    lhu t0, 0(a0)
    lhu t1, 0(a1)
    slli t0, t0, 16
    slli t1, t1, 16
    fmv.w.x ft0, t0
    fmv.w.x ft1, t1
    fmadd.s fa0, ft0, ft1, fa0, rne
    addi a0, a0, 2
    addi a1, a1, 2
    addi a2, a2, -1
    bnez a2, .Lbf_loop
.Lbf_done:
    ret
.size dot_bf16_fma, .-dot_bf16_fma

# float dot_fp32_sep(const float *x, const float *w, size_t n)
# Separate rounding of product and sum: the Delta recurrence uses this order.
.globl dot_fp32_sep
.type dot_fp32_sep,@function
dot_fp32_sep:
    fmv.w.x fa0, zero
    beqz a2, .Lsep_done
.Lsep_loop:
    flw ft0, 0(a0)
    flw ft1, 0(a1)
    fmul.s ft2, ft0, ft1, rne
    fadd.s fa0, fa0, ft2, rne
    addi a0, a0, 4
    addi a1, a1, 4
    addi a2, a2, -1
    bnez a2, .Lsep_loop
.Lsep_done:
    ret
.size dot_fp32_sep, .-dot_fp32_sep

# float rms_inverse_fp32(const float *x, size_t n, float epsilon)
# a0=x, a1=n, fa0=epsilon. Precondition: 1<=n<=2^24; finite inputs.
# Only returns 1/sqrt(mean(x*x)+epsilon); affine and BF16 casts are separate.
.globl rms_inverse_fp32
.type rms_inverse_fp32,@function
rms_inverse_fp32:
    mv t0, a1
    fmv.w.x ft0, zero
.Lrms_loop:
    flw ft1, 0(a0)
    fmul.s ft2, ft1, ft1, rne
    fadd.s ft0, ft0, ft2, rne
    addi a0, a0, 4
    addi t0, t0, -1
    bnez t0, .Lrms_loop
    fcvt.s.lu ft1, a1, rne
    fdiv.s ft0, ft0, ft1, rne
    fadd.s ft0, ft0, fa0, rne
    fsqrt.s ft0, ft0, rne
    li t0, 0x3f800000
    fmv.w.x ft1, t0
    fdiv.s fa0, ft1, ft0, rne
    ret
.size rms_inverse_fp32, .-rms_inverse_fp32
