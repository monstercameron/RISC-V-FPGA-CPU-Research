/* SPDX-License-Identifier: MIT
 * Minimal freestanding errno.h: 7zTypes.h maps a few Windows error names to
 * these values. The benchmark never reads errno.
 */
#ifndef BENCH_LZMA_ERRNO_H
#define BENCH_LZMA_ERRNO_H

#define ENOENT 2
#define EEXIST 17
#define EINVAL 22
#define ENOSPC 28

#endif
