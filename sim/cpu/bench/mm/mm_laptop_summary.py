"""Summarise mm_laptop.sh output: per kernel the median of the runs' medians with min-max.

Usage: python3 mm_laptop_summary.py LOG [EXPECTED_JSON]
A run is dropped when its peak probe (independent adds) retires fewer instructions per clock than 0.9 x the median probe (the
vCPU was on a smaller core), or when its checksum words differ from EXPECTED_JSON's mailbox words.
SPDX-License-Identifier: MIT
"""
import json
import statistics
import sys

MIN_PROBE_FRACTION = 0.9  # of the median probe


def main():
    runs, header = [], None
    for line in open(sys.argv[1], encoding='utf-8'):
        line = line.strip()
        if line.startswith('{'):
            item = json.loads(line)
            if 'words' in item:
                header = {'probe': item['peak_probe_ipc'], 'cpu': item['cpu'], 'words': item['words'], 'kernels': {}}
                runs.append(header)
            elif header is not None:
                header['kernels'][item['kernel']] = item
    want = None
    if len(sys.argv) > 2:
        want = [v for _, v in sorted(json.load(open(sys.argv[2]))['mailbox'].items(), key=lambda kv: int(kv[0]))]
    probes = sorted(r["probe"] for r in runs)
    floor = MIN_PROBE_FRACTION * probes[len(probes) // 2]
    kept = [r for r in runs if r["probe"] >= floor and (want is None or r["words"] == want)]
    print(f'{len(runs)} runs, {len(kept)} kept (probe >= {floor:.2f} instr/clk, 0.9 x the median'
          f'{", checksums equal the native reference" if want else ""}); probes '
          f'{[round(r["probe"], 2) for r in runs]}')
    names = list(kept[0]['kernels']) if kept else []
    for name in names:
        rows = [r['kernels'][name] for r in kept]
        entry = {}
        for key in ('cycles', 'instructions', 'macs_per_clk', 'bytes_per_clk', 'ipc'):
            if key in rows[0]:
                values = [x[key] for x in rows]
                entry[key] = (statistics.median(values), min(values), max(values))
        text = f'{name}: cycles {entry["cycles"][0]:,.0f} [{entry["cycles"][1]:,.0f}-{entry["cycles"][2]:,.0f}], ' \
               f'{entry["instructions"][0]:,.0f} instr, IPC {entry["ipc"][0]:.2f}, ' \
               f'{entry["macs_per_clk"][0]:.4f} MAC/clk [{entry["macs_per_clk"][1]:.4f}-{entry["macs_per_clk"][2]:.4f}]'
        if 'bytes_per_clk' in entry:
            text += f', {entry["bytes_per_clk"][0]:.4f} B/clk [{entry["bytes_per_clk"][1]:.4f}-{entry["bytes_per_clk"][2]:.4f}]'
        print(text)


if __name__ == '__main__':
    main()
