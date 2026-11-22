/* SPDX-License-Identifier: MIT
 * Portable math for the ray-tracing benchmark (rt_math.c), so the native
 * reference build and the bare-metal RV64 builds compute bit-identical results:
 *   rt_sqrt  correctly rounded (hardware square root where the target has one,
 *            otherwise an integer bit-by-bit square root: identical results);
 *   rt_sin, rt_cos  own Cody-Waite reduction and Taylor polynomials, the same
 *            code on every target (not glibc's, so images differ in the last
 *            bits from the laptop reference build that used glibc);
 *   rt_fabs  sign-bit clear.
 * Every caller is compiled with -ffp-contract=off.
 */
#ifndef RT_MATH_H
#define RT_MATH_H

#ifdef __cplusplus
extern "C" {
#endif

double rt_sqrt(double x);
double rt_sin(double x);
double rt_cos(double x);
double rt_fabs(double x);

#ifdef __cplusplus
}
#endif

#define RT_PI 3.14159265358979323846

#endif
