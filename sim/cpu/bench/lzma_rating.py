"""7-Zip benchmark ratings for LZMA, from instruction-equivalent "commands".

Translated from 7-Zip 26.06, CPP/7zip/UI/Common/Bench.cpp
(https://github.com/ip7z/7zip, commit d3296e39e1f1f92c7b41c0c3848e65640428d42d):
GetLogSize(), GetLogSize_Sub(), CBenchProps::SetLzmaCompexity(),
GetNumCommands_Enc/Dec() and GetRating_Enc/Dec(). 7-Zip Copyright (C) 1999-2026
Igor Pavlov; Bench.cpp states no licence of its own, so by 7-Zip's DOC/License.txt
it is under the GNU LGPL, version 2.1 or later, which this file keeps
(licenses/7ZIP-License.txt, licenses/7ZIP-LGPL-2.1.txt).

7-Zip reports rating = commands * timer_frequency / elapsed_ticks, printed in
MIPS. With elapsed time = clocks / f, rating / f = commands / clocks, so the
"MIPS per MHz" figure here is commands per clock and needs no clock frequency.
SPDX-License-Identifier: LGPL-2.1-or-later
"""

SUB_BITS = 8                # kSubBits
BENCH_MIN_DIC_LOG_SIZE = 18  # kBenchMinDicLogSize (Bench.h)
ENC_COMPLEX = 1200          # SetLzmaCompexity(); replaced by the dictionary formula below
DEC_COMPLEX_UNC = 4
DEC_COMPLEX_COMPR = 190


def get_log_size(size):
    i = 0
    while True:
        i += 1
        size >>= 1
        if size == 0:
            return i


def get_log_size_sub(size):
    if size <= 1:
        return 0
    i = get_log_size(size) - 1
    v = (size << (SUB_BITS - i)) if i <= SUB_BITS else (size >> (i - SUB_BITS))
    return (i << SUB_BITS) + (v & ((1 << SUB_BITS) - 1))


def encode_complexity(dict_size):
    """Commands per input byte for LZMA compression (LzmaRatingMode)."""
    dict_size = max(dict_size, 1 << BENCH_MIN_DIC_LOG_SIZE)
    t = (get_log_size_sub(dict_size) - (BENCH_MIN_DIC_LOG_SIZE << SUB_BITS)) & 0xffffffff
    return 870 + ((t * t * 5) >> (2 * SUB_BITS))


def encode_commands(unpack_size, dict_size):
    """GetRating_Enc() numerator. 7-Zip's GetRating_Enc() uses the full size;
    only the iteration count (GetNumCommands_Enc) clamps it to 100 bytes."""
    return unpack_size * encode_complexity(dict_size)


def decode_commands(pack_size, unpack_size):
    return pack_size * DEC_COMPLEX_COMPR + unpack_size * DEC_COMPLEX_UNC


def rating_per_mhz(commands, clocks):
    """7-Zip rating in MIPS divided by the clock in MHz: commands per clock."""
    return commands / clocks
