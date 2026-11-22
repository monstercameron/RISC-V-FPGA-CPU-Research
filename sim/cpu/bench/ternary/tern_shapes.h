/* SPDX-License-Identifier: MIT
 * Shapes of the ternary benchmark (shared by the native generator, the laptop reference and the
 * RISC-V program). TERN_SHAPE 1 is T-small, TERN_SHAPE 0 is T-2B4T. y[m] = sum_k w[m][k] * a[k].
 *   T-small  three layers, 1,179,648 weights (RTL scale)
 *   T-2B4T   one BitNet b1.58 2B4T decoder layer (hidden 2560, FFN 6912, 20 heads of 128, 5 KV
 *            heads): Q, K and V merged (3840 x 2560), O (2560 x 2560), gate and up merged
 *            (13824 x 2560), down (2560 x 6912): 69,468,160 weights
 */
#ifndef TERN_SHAPES_H
#define TERN_SHAPES_H
typedef struct { int m, k; } tern_layer_t;
#ifndef TERN_SHAPE
#define TERN_SHAPE 1
#endif
#if TERN_SHAPE == 1
static const tern_layer_t TERN_LAYERS[] = { {256, 1280}, {512, 1024}, {128, 2560} };
#define TERN_MAXM 512
#define TERN_MAXK 2560
#elif TERN_SHAPE == 0
static const tern_layer_t TERN_LAYERS[] = { {3840, 2560}, {2560, 2560}, {13824, 2560}, {2560, 6912} };
#define TERN_MAXM 13824
#define TERN_MAXK 6912
#else
#error "TERN_SHAPE must be 0 (T-2B4T) or 1 (T-small)"
#endif
#define TERN_NL ((int)(sizeof TERN_LAYERS / sizeof TERN_LAYERS[0]))
/* kernel slots (bit n of the kernel mask) */
enum { TS_I2 = 0, TS_LUT5W = 1, TS_BS8 = 2, TS_STREAM = 3, TS_STREAMALL = 4, TS_N = 5 };
#endif
