# SPDX-License-Identifier: MIT
# Required RVA23 instructions only. These are not a complete inference runtime.
.text
.option norvc
.option norelax

# void gemv_bf16_rvv(const uint16_t *W, const uint16_t *x,
#                    float *y, size_t M, size_t K)
# a0=W[K][M] (k-major), a1=x[K], a2=y[M], a3=M, a4=K.
# Each lane is an output row; increasing k preserves the FMA recurrence.
# Result is FP32 BEFORE optional bias and mandatory projection BF16 rounding.
# The full packed model must NOT be expanded to FP32 for this example.
.globl gemv_bf16_rvv
.type gemv_bf16_rvv,@function
gemv_bf16_rvv:
    beqz a3, .Lgemv_return
    csrrwi a7, frm, 0
    slli a5, a3, 1
.Lgemv_rows:
    vsetvli t0, a3, e32, m2, ta, ma
    vmv.v.i v12, 0
    mv t1, a0
    mv t2, a1
    mv t3, a4
    beqz t3, .Lgemv_store
.Lgemv_k:
    # EEW16 load has EMUL1 while SEW32/LMUL2 stays unchanged.
    vle16.v v8, (t1)
    vzext.vf2 v10, v8
    vsll.vi v10, v10, 16
    lhu t4, 0(t2)
    slli t4, t4, 16
    fmv.w.x ft0, t4
    vfmacc.vf v12, ft0, v10
    add t1, t1, a5
    addi t2, t2, 2
    addi t3, t3, -1
    bnez t3, .Lgemv_k
.Lgemv_store:
    vse32.v v12, (a2)
    slli t1, t0, 1
    add a0, a0, t1
    slli t1, t0, 2
    add a2, a2, t1
    sub a3, a3, t0
    bnez a3, .Lgemv_rows
    csrw frm, a7
.Lgemv_return:
    ret
.size gemv_bf16_rvv, .-gemv_bf16_rvv

# void delta_update_row_fp32(const float *old, const float *delta,
#                            float *updated, size_t n, float decay, float k)
# a0/a1/a2/a3 and fa0/ fa1. delta must already use prediction from ALL Sd rows.
# updated may equal old exactly; otherwise buffers are disjoint.
# Separate mul/add is intentional. Readout must subsequently use updated state.
.globl delta_update_row_fp32
.type delta_update_row_fp32,@function
delta_update_row_fp32:
    beqz a3, .Ldelta_return
    csrrwi a7, frm, 0
.Ldelta_loop:
    vsetvli t0, a3, e32, m1, ta, ma
    vle32.v v8, (a0)
    vle32.v v9, (a1)
    vfmul.vf v8, v8, fa0
    vfmul.vf v9, v9, fa1
    vfadd.vv v10, v8, v9
    vse32.v v10, (a2)
    slli t1, t0, 2
    add a0, a0, t1
    add a1, a1, t1
    add a2, a2, t1
    sub a3, a3, t0
    bnez a3, .Ldelta_loop
    csrw frm, a7
.Ldelta_return:
    ret
.size delta_update_row_fp32, .-delta_update_row_fp32
