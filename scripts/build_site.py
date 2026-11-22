#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate the static gallery site in docs/ from the repository's own records.

Reads (never writes): cpu/VERSION, cpu/architecture.md (section 9 history table),
DEVLOG.md (days, findings, timeline, commits, run index) and `git tag -l "cpu-v*"`
(read-only). Writes only generated files under docs/:

    docs/data/versions.json, docs/data/journal.json
    docs/art/v<version>.svg            one generated artwork per architecture version
    docs/index.html, docs/gallery.html, docs/journal.html

docs/assets/ (style.css, site.js) is hand-written and is not touched.

Usage: python -B scripts/build_site.py
The output is deterministic: no clock, no randomness beyond seeded generators.
"""
from __future__ import annotations

import html
import json
import math
import random
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "docs"
REPO_URL = "https://github.com/monstercameron/RISC-V-FPGA-CPU-Research"
BLOB = REPO_URL + "/blob/main/"

# Palette (also in docs/assets/style.css)
PAPER, INK = "#f3ead7", "#1f1b17"
OCHRE, OXBLOOD, SLATE, SAGE, GOLD = "#c58f2c", "#7a2430", "#3f5a73", "#7f9168", "#b8923a"

MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
             "août", "septembre", "octobre", "novembre", "décembre"]


def e(s) -> str:
    return html.escape(str(s), quote=True)


def fr_date(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d}{'er' if d == 1 else ''} {MONTHS_FR[m - 1]} {y}"


# ---------------------------------------------------------------------------
# Inline markdown to HTML (enough for the log's own style)
# ---------------------------------------------------------------------------

def link_target(u: str) -> str:
    if re.match(r"https?://", u):
        return u
    if u.startswith("#run-logs") or u == "#run-logs":
        return "journal.html#runs"
    if u.startswith("#"):
        return BLOB + "DEVLOG.md" + u
    return BLOB + u.lstrip("./").replace("\\", "/")


def md_inline(s: str) -> str:
    s = s.replace("\\|", "|")
    out, pos = [], 0
    for m in re.finditer(r"`([^`]+)`", s):
        out.append(("t", s[pos:m.start()]))
        out.append(("c", m.group(1)))
        pos = m.end()
    out.append(("t", s[pos:]))
    res = []
    for kind, txt in out:
        if kind == "c":
            res.append(f"<code>{e(txt)}</code>")
            continue
        t = e(txt)
        t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
                   lambda m: f'<a href="{e(link_target(html.unescape(m.group(2))))}" rel="noopener">{m.group(1)}</a>', t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
        res.append(t)
    return "".join(res)


def md_plain(s: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = s.replace("`", "").replace("**", "").replace("\\|", "|")
    return s


def shorten(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0].rstrip(",;:. ")
    return cut + "…"


# ---------------------------------------------------------------------------
# Reading the repository
# ---------------------------------------------------------------------------

def split_row(line: str) -> list[str]:
    cells, cur, tick, i = [], "", False, 0
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            cur += "|"
            i += 2
            continue
        if ch == "`":
            tick = not tick
        if ch == "|" and not tick:
            cells.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    cells.append(cur.strip())
    return cells


def git_tags() -> set[str]:
    try:
        r = subprocess.run(["git", "tag", "-l", "cpu-v*"], cwd=ROOT, capture_output=True,
                           text=True, check=True, timeout=30)
        return {t.strip()[len("cpu-v"):] for t in r.stdout.splitlines() if t.strip()}
    except Exception:
        return set()


def read_history() -> list[dict]:
    text = (ROOT / "cpu" / "architecture.md").read_text(encoding="utf-8")
    start = text.index("### History")
    rows = []
    for line in text[start:].splitlines()[1:]:
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = split_row(line)
        if len(cells) < 6 or not re.match(r"^\d+\.\d+\.\d+$", cells[0]):
            continue
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", cells[1])
        rows.append({
            "version": cells[0],
            "date": dates[-1] if dates else "",
            "date_text": cells[1],
            "summary": md_plain(cells[3]),
            "summary_html": md_inline(cells[3]),
            "breaking": md_plain(cells[4]),
        })
    return rows


def read_runs() -> list[dict]:
    text = (ROOT / "DEVLOG.md").read_text(encoding="utf-8")
    i = text.find("## Run logs")
    runs = []
    if i < 0:
        return runs
    for line in text[i:].splitlines():
        if not line.startswith("|"):
            continue
        c = split_row(line)
        if len(c) < 9 or not re.match(r"^\d{4}-\d{2}-\d{2}", c[0]):
            continue
        try:
            clocks = float(c[5].replace(",", ""))
            dm = float(c[6])
        except ValueError:
            continue
        comp = md_plain(c[4])
        runs.append({
            "time": c[0], "commit": md_plain(c[1]), "uncommitted": c[2], "version": c[3],
            "compiler": comp, "clocks": clocks, "dmips_mhz": dm,
            "fast": "fast runtime" in comp,
        })
    return runs


def read_journal() -> list[dict]:
    lines = (ROOT / "DEVLOG.md").read_text(encoding="utf-8").splitlines()
    days, cur, section = [], None, None
    in_code = False
    commit = None
    for ln in lines:
        if ln.startswith("```"):
            in_code = not in_code
            if in_code and commit is not None and cur is not None and "subject" not in commit:
                commit["_want"] = True
            continue
        if in_code:
            if commit is not None and commit.get("_want") and ln.strip():
                commit["subject"] = ln.strip()
                commit.pop("_want", None)
            continue
        m = re.match(r"^## (\d{4}-\d{2}-\d{2}): (.*)$", ln)
        if m:
            cur = {"date": m.group(1), "title": md_plain(m.group(2)), "findings": [],
                   "timeline": [], "commits": []}
            days.append(cur)
            section, commit = None, None
            continue
        if ln.startswith("## "):
            cur, section, commit = None, None, None
            continue
        if cur is None:
            continue
        if ln.startswith("### "):
            section = ln[4:].strip()
            commit = None
            continue
        if section == "Findings":
            m = re.match(r"^(?:\d+\.|-)\s+(.*)$", ln)
            if m:
                cur["findings"].append(m.group(1).strip())
            elif ln.strip() and cur["findings"] and ln.startswith("  "):
                cur["findings"][-1] += " " + ln.strip()
        elif section == "Timeline":
            if ln.startswith("|") and not ln.startswith("|---") and not ln.startswith("| Time"):
                c = split_row(ln)
                if len(c) >= 3:
                    cur["timeline"].append({"time": md_plain(c[0]),
                                            "text": "|".join(c[1:-1]).strip(),
                                            "kind": md_plain(c[-1])})
                elif len(c) == 2 and c[1]:
                    # Some rows give only the time and the event, with no source
                    # column; keep them, and show no source tag rather than guess one.
                    cur["timeline"].append({"time": md_plain(c[0]), "text": c[1].strip(), "kind": ""})
        elif section == "Commits":
            m = re.match(r"^#### `([0-9a-f]{7,40})`, (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}), (.*)$", ln)
            if m:
                commit = {"hash": m.group(1), "date": m.group(2), "time": m.group(3),
                          "author": m.group(4).strip()}
                cur["commits"].append(commit)
            elif ln.startswith("#### "):
                commit = None
    for d in days:
        for c in d["commits"]:
            c.pop("_want", None)
            c.setdefault("subject", "")
    return days


# ---------------------------------------------------------------------------
# What each version drew from the sources. Every number below is from the
# architecture history rows (cpu/architecture.md section 9), section 1's table,
# or the RTL's own parameters at that tag. Anything else is left qualitative.
# ---------------------------------------------------------------------------

DEFAULTS = dict(
    kind="mc", fetch_w=2, fetch_buf=False, icache_kb=None, dcache_kb=None, dc_ways=1,
    issue=1, retire=1, slot2=[], folding=False, mul=False, div=False, bext=False,
    states=["FETCH", "EXECUTE", "MEMORY"], stages=[], btb=0, ras=0, fq=False,
    rob=0, prf=0, iq=0, decode_w=0, alus=0, full=0, loads=0, stores=0, ldst_shared=False,
    fwd=False, snapshots=False, taken=0, loop=False, vp=False, predecode=False, paired=False,
    marks=[], fuse=False, bias=False, btb_n=256, lp_n=256,
    mul_lat=0, ld_knob=False, l2=False, vp_conf=False, tage=False,
    tg_n=4, btb_guard=False, btb_rel=False, l0=False, ldwait=False, n_miss=False, fuse_x=False,
    wake_fill=False, fpu=False, fp_lat=False, fp_div=False,
)

# (version, era, French title, caption, medium, overrides)
WORKS = [
    ("0.1.0", "Le Premier Souffle",
     "One instruction at a time, drawn in three breaths: fetch, execute, remember. No cache, no predictor.",
     dict()),
    ("0.1.1", "Le Tampon",
     "The last beat fetched is kept, and the next instruction often finds it already there.",
     dict(fetch_buf=True, marks=["a one-beat fetch buffer"])),
    ("0.2.0", "La Bibliothèque",
     "A small library of instructions replaces the buffer: 4 KiB, direct-mapped, 8-byte lines.",
     dict(fetch_buf=False, icache_kb=4)),
    ("0.2.1", "L'Impatience",
     "Loads and stores send their request from EXECUTE instead of waiting a clock.",
     dict(marks=["requests issue from EXECUTE"])),
    ("0.2.2", "L'Accusé",
     "The memory acknowledges a write in the clock it is offered; stores now retire at once.",
     dict(marks=["writes acknowledged in the same clock"])),
    ("0.3.0", "Le Miroir",
     "A data cache for loads, 4 KiB and write-through, answers what the bus used to.",
     dict(dcache_kb=4)),
    ("0.4.0", "L'Arithmétique",
     "The M extension arrives: multiply and a divider that steps once per clock.",
     dict(mul=True, div=True, states=["FETCH", "EXECUTE", "MEMORY", "DIVIDE"])),
    ("0.5.0", "Le Duo",
     "Two instructions in one clock: a second slot and a second retirement port.",
     dict(issue=2, retire=2, slot2=["simple integer"])),
    ("0.5.1", "Le Pont",
     "The second slot may reach into the next beat, and may be a conditional branch.",
     dict(fetch_w=4, slot2=["simple integer", "branch"], marks=["second slot across beats"])),
    ("0.5.2", "Deux Lectures",
     "A second data-cache port lets an aligned load ride in the second slot.",
     dict(slot2=["simple integer", "branch", "load"], marks=["second data-cache port"])),
    ("0.5.3", "Le Saut",
     "Jumps may take the second slot; a not-taken branch may lead the pair.",
     dict(slot2=["simple integer", "branch", "load", "jump"], marks=["jump in the second slot"])),
    ("0.5.4", "Le Relais",
     "Stores join the second slot, and results are passed hand to hand within the clock.",
     dict(slot2=["simple integer", "branch", "load", "jump", "store"], marks=["slot-to-slot forwarding"])),
    ("0.5.5", "Le Repli",
     "Branch folding: a jump and the instruction at its target execute together.",
     dict(folding=True, marks=["branch folding"])),
    ("0.6.0", "La Grammaire des Bits",
     "The B extension (Zba, Zbb, Zbs) enters both slots; three multipliers become one.",
     dict(bext=True)),
    ("0.7.0", "Le Trio",
     "A third, ALU-only slot and a third retirement port: three instructions in a clock.",
     dict(issue=3, retire=3)),
    ("0.7.1", "Le Temps Compté",
     "The multiplier is registered: one clock longer, and the longest path shortens from 80 to 52 LUT levels.",
     dict(states=["FETCH", "EXECUTE", "MEMORY", "DIVIDE", "MULTIPLY"], marks=["registered multiplier"])),
    ("0.8.0", "La Chaîne",
     "A second implementation: a four-stage single-issue pipeline with a 256-entry branch target buffer.",
     dict(kind="pipe", states=[], stages=["F", "D", "E", "M"], btb=256, ras=4, fetch_w=1,
          issue=1, retire=1, slot2=[], folding=False)),
    ("0.8.1", "L'Antichambre",
     "A fetch queue between F and D, split redirects, and an extra stage for slow bus accesses.",
     dict(stages=["F", "D", "E", "M", "X"], fq=True, marks=["fetch queue and X stage"])),
    ("0.9.0", "Le Désordre",
     "A third implementation, out of order: rename, a 32-entry reorder buffer and an 8-entry issue queue.",
     dict(kind="ooo", stages=[], rob=32, prf=64, iq=8, decode_w=1, fetch_w=1, alus=1, full=0,
          loads=1, stores=0, ldst_shared=True, retire=1)),
    ("0.9.1", "Le Passage des Valeurs",
     "A load may take its value straight from an older store still waiting to retire.",
     dict(fwd=True, marks=["store-to-load forwarding"])),
    ("0.9.2", "Les Jumeaux",
     "Two-wide: two fetched, two renamed, two integer ports, two retired per clock.",
     dict(fetch_w=2, decode_w=2, alus=2, retire=2, issue=2)),
    ("0.9.3", "Le Dernier Mot",
     "Stores read their data at retirement and no longer make the head of the line wait.",
     dict(marks=["stores finish at retirement"])),
    ("0.9.4", "Par-dessus la Frontière",
     "Fetch reads the next beat too, so a pair may straddle a boundary.",
     dict(marks=["cross-beat fetch"])),
    ("0.10.0", "L'Octuple",
     "Eight wide, sized after published measurements of the Apple M5 performance core: "
     "128-entry reorder buffer, 160 physical registers, 64-entry issue queue, 8 ALUs (3 full), 3 load and 2 store ports.",
     dict(fetch_w=8, decode_w=8, retire=8, issue=8, rob=128, prf=160, iq=64, alus=8, full=3,
          loads=3, stores=2, ldst_shared=False, icache_kb=128, dcache_kb=128, snapshots=True, taken=1)),
    ("0.10.1", "Le Double Saut",
     "Fetch follows two predicted-taken transfers in one clock.",
     dict(taken=2)),
    ("0.11.0", "La Boucle",
     "A loop predictor, a two-way data cache and paired store writes on the bus.",
     dict(loop=True, dc_ways=2, paired=True)),
    ("0.11.1", "Le Pressentiment",
     "Value prediction for loads, multiplies and divides; fetch predecode of direct jumps, calls and returns.",
     dict(vp=True, predecode=True)),
    ("0.11.2", "L'Alliage",
     "A simple operation and the instruction that reads its result are welded into one; "
     "the loop predictor and the branch buffer grow fourfold to 1,024 entries, and a branch that has always gone one way is trusted to go on.",
     dict(fuse=True, bias=True, btb_n=1024, lp_n=1024,
          marks=["instruction fusion", "1,024-entry predictors", "fixed-direction bias"])),
    ("0.12.0", "Les Seize Voix",
     "Sixteen instructions a clock through fetch, rename and retirement, before a window twice the size: "
     "256 in the reorder buffer, 288 physical registers, 128 waiting. Behind it the same eight execution units, unchanged.",
     dict(fetch_w=16, decode_w=16, retire=16, issue=16, rob=256, prf=288, iq=128,
          marks=["sixteen lanes"])),
    ("0.12.1", "La Réparation",
     "A small mending: the scan that sends stores to memory now stops exactly where retirement stops, "
     "so a store behind a wrongly guessed value can no longer slip out unretired. Found by a reviewer, mended by the memory engineer.",
     dict(marks=["one rule for stores and retirement"])),
    ("0.12.2", "Les Quatre Tournants",
     "The council's first gain: fetch follows four taken turns and holds four calls and returns in one clock.",
     dict(taken=4, marks=["four taken turns"])),
    ("0.12.3", "Le Pliage",
     "The simplest instructions (moves, constants, small additions, direct jumps) are folded at rename into a register and an offset; "
     "a third of the program never reaches an execution unit.",
     dict(marks=["folded at rename"])),
    ("0.13.0", "Les Quatre Lettres",
     "Up to four stores leave together in one write, and store addresses are worked out before the loads of the same clock.",
     dict(marks=["four stores a write"])),
    ("0.13.1", "Les Sept Portes",
     "Seven doors to memory: four for loads, three for store addresses, so the wide front end is no longer kept waiting at the threshold.",
     dict(loads=4, stores=3, marks=["four loads, three stores a clock"])),
    ("0.14.0", "La Grande Salle",
     "The waiting room doubles to 512 places, and thirty-two instructions may take their leave in one clock.",
     dict(rob=512, prf=544, retire=32, marks=["512 in flight", "thirty-two retire"])),
    ("0.14.1", "Le Grand Souffle",
     "Fetch and rename breathe thirty-two at a time. In simulation the word-wise Dhrystone passes twenty-seven DMIPS per MHz.",
     dict(fetch_w=32, decode_w=32, marks=["thirty-two lanes"])),
    ("0.14.2", "Le Raccommodage",
     "A mending after an outside review: the store-write range is checked, the return-stack pointer is restored from the offending load's own entry, "
     "and only a load that truly read bytes can be marked as a violator. The speed is unchanged.",
     dict(marks=["mended after review"])),
    ("0.14.3", "Le Pressentiment des Chiffres",
     "Rename now computes what it already knows: simple operations on constants are worked out on the spot, and branches whose operands are known are decided there, "
     "so such instructions never wait for an execution unit.",
     dict(marks=["constants and branches decided at rename"])),
    ("0.14.4", "La Pile Profonde",
     "The return stack deepens from sixteen to sixty-four entries, so a long chain of calls still finds its way home.",
     dict(ras=64, marks=["64-entry return stack"])),
    ("0.14.5", "La Profondeur",
     "A dial for honesty: the fetch path can be made as deep as a real core's, so a wrong guess costs ten clocks instead of three. "
     "Set to zero the drawing is unchanged; set to eight it shows what a buildable pipeline would lose.",
     dict(marks=["front-end depth dial"])),
    ("0.14.6", "La Quatrième Main",
     "A fourth of the eight hands learns to judge a branch, and those hands now turn to branches before plain arithmetic. "
     "The multiply queue is cut to the number of ports, so none is dropped as they grow. A small gain, in simulation: 15,658 / 10,202 clocks.",
     dict(full=4, marks=["four branch-capable ports"])),
    # Salle VIII: the council's 7-Zip phase. Figures from the 0.14.7 to 0.15.2 history rows.
    ("0.14.7", "La Main Leste",
     "The multiplier answers in two clocks instead of three: a behavioural assumption, its DSP timing not yet proven. "
     "On the scaled 7-Zip kernel, compression rises from 7.46 to 7.65 MIPS per MHz and decompression from 2.89 to 3.23, in simulation; Dhrystone does not move.",
     dict(mul_lat=2, marks=["two-clock multiply"])),
    ("0.14.8", "Le Juste Prix",
     "A mending for honesty, after the outside reviewer: an instruction folded onto a multiply, a divide or a guessed value now pays its one clock of offset. "
     "The scaled kernel barely stirs, 473,002 to 473,020 clocks; the drawing is truer, not faster.",
     dict(marks=["the offset clock paid"])),
    ("0.14.9", "Le Fil d'Ariane",
     "After a wrong turn, the return stack's top entry is restored together with its pointer, so the thread home is not lost. "
     "Return mispredictions in compression fall from 1,894 to 9, and the scaled kernel compresses at 7.72 MIPS per MHz.",
     dict(marks=["return stack restored whole"])),
    ("0.14.10", "Le Cadran des Lectures",
     "A second dial: loads may be made to answer later, as a real memory would. Left at one clock, nothing changes; "
     "turned to four, the scaled kernel needs about 630,600 / 178,600 clocks instead of 468,772 / 135,703.",
     dict(ld_knob=True, marks=["load-latency dial"])),
    ("0.14.11", "Le Retour Décalé",
     "A return that lands a little past its call is now predicted as the popped address plus its displacement; every such return was missed before. "
     "Neither benchmark contains one, so neither moves.",
     dict(marks=["displaced returns"])),
    ("0.14.12", "La Seconde Quittance",
     "The same honesty for slow loads: when the dial makes a load answer late, an instruction folded onto it pays its offset clock too. "
     "At the default one-clock load nothing changes.",
     dict(marks=["offset clock after slow loads"])),
    ("0.14.13", "Le Pas Repris",
     "In the very clock a branch is corrected, fetch already reads one cached beat of the right target. "
     "The scaled kernel: 7.76 MIPS per MHz compressing, 3.25 decompressing.",
     dict(marks=["fetch in the recovery clock"])),
    ("0.15.0", "Les Étages",
     "The house gains floors below: the system may now be given a second-level cache and a distant memory, each with its own delay. "
     "By default the floors are closed and every count is as before; opened to a 1 MiB second level and a memory a hundred clocks away, "
     "the scaled kernel slows to 6.43 / 2.67 MIPS per MHz.",
     dict(l2=True, marks=["second level and distant memory"])),
    ("0.15.1", "La Confiance",
     "A guessed value must now earn trust: thirty-two equal results before it is used, twice as many after each wrong guess, up to sixty-four. "
     "Wrong guesses in compression fall from 1,953 to 86, and the scaled kernel compresses at 7.97 MIPS per MHz.",
     dict(vp_conf=True, marks=["value prediction earns trust"])),
    ("0.15.2", "La Longue Mémoire",
     "A predictor that remembers the road: four tagged tables of 1,024 entries, looking back 5, 15, 44 and 128 steps of global history, about 18.4 KiB. "
     "Compression on the scaled kernel leaps from 7.97 to 9.16 MIPS per MHz; Dhrystone's reference run is half a percent slower.",
     dict(tage=True, marks=["global-history predictor"])),
    # Salle IX: mendings and second memories. Figures from the 0.15.3 to 0.16.1 history rows
    # (and, for the six history lengths drawn in 0.15.7, the RTL's tg_len at tag cpu-v0.15.7).
    ("0.15.3", "Le Garde-Fou",
     "A guard rail for the branch buffer: a hit is believed only where a branch, a jump or a jump-and-link truly stands. "
     "An old entry left behind by rewritten code no longer turns fetch aside; in the new test, twenty wrong redirects become none. 7-Zip and Dhrystone do not move.",
     dict(btb_guard=True, marks=["BTB hits for transfers only"])),
    ("0.15.4", "La Mémoire Proche",
     "A dial for a near memory: the beats most recently read by loads may be kept close at hand, answering in two clocks when the first level is made slower. "
     "Off by default, and nothing moves; with loads at four clocks on 0.15.1, sixteen beats save 6.5% / 8.5% of the scaled kernel's clocks, thirty-two save 8.3% / 9.3%.",
     dict(l0=True, marks=["recent-beat buffer dial"])),
    ("0.15.5", "Le Chemin Relatif",
     "Branch targets are remembered as a signed distance from the branch, two gibibytes either way, and an entry that cannot reach is forgotten. "
     "Of eight branch and target pairs, the old way was wrong for five. The benchmarks do not move.",
     dict(btb_rel=True, marks=["PC-relative targets"])),
    ("0.15.6", "Le Registre des Attentes",
     "A ledger of loads that once ran ahead of a store and were caught: 4,096 entries, wiped clean every 65,536 clocks. "
     "The scaled kernel compresses at 9.20 MIPS per MHz and decompresses at 3.28, in simulation.",
     dict(ldwait=True, marks=["load-wait table"])),
    ("0.15.7", "Les Six Mémoires",
     "The long-memory predictor gains two tables: six, looking back from 4 to 128 steps, about 22.4 KiB in all, and now every entry ages. "
     "Compression on the scaled kernel reaches 9.37 MIPS per MHz.",
     dict(tg_n=6, marks=["six tagged tables"])),
    ("0.16.0", "Les Lettres en Vol",
     "Several letters in flight: the data side may send up to eight reads at once, each with its own tag, and their answers return on a channel of their own, in any order. "
     "The oldest load keeps its reserved place. At the default of one, every count is as before; with a 1 MiB second level, a memory a hundred clocks away and four in flight, "
     "compression on the scaled kernel rises from 7.56 to 8.30 MIPS per MHz, under stated optimistic assumptions.",
     dict(n_miss=True, marks=["several reads in flight", "split read channel"])),
    ("0.16.1", "Le Trait d'Union",
     "A simple operation and the one that reads it are welded even when they arrive a clock apart: the waiting producer is held over, in a single register, into the next rename. "
     "The scaled kernel reaches 9.41 / 3.29 MIPS per MHz, and a larger waiting room is no longer slower.",
     dict(fuse_x=True, marks=["fusion across rename groups"])),
    ("0.16.2", "Le Réveil",
     "A load that missed no longer knocks again and again: each younger missed load sleeps until the answer for its own beat comes back, and wakes. "
     "At the default of one read in flight the counts barely move; with a 1 MiB second level, a memory a hundred clocks away and four reads in flight, "
     "a 4 KiB data cache compresses in 4.3% fewer clocks, in simulation.",
     dict(wake_fill=True, marks=["wake on fill"])),
    # Salle X: numbers that float. Figures from the 0.17.0 history row; the port split
    # (two FMA, two misc) from the DEVLOG.md rows of 2026-11-21 23:38 and 00:53.
    ("0.17.0", "La Virgule Flottante",
     "Numbers that float: single and double precision join the out-of-order core behind a build switch, off by default. "
     "Four floating-point ports, a divide and square root that accept new work before the last is done, one rename map of sixty-four names, "
     "and the exception flags settled at retirement. Hard-float ray tracing finds 3.57 primary rays per thousand clocks where soft float found 0.327, "
     "and 315 paths per million clocks where it found 15.4, in simulation; built in, the unit leaves Dhrystone and 7-Zip clocks unchanged.",
     dict(fpu=True, marks=["F and D, off by default", "fflags at retirement"])),
    # Figures from the 0.17.1 and 0.17.2 history rows (ray tracing in full mode, contiguous
    # from reset; not the sampled deciding-config RT-T rates withdrawn at DEVLOG.md 01:08 / 01:11).
    ("0.17.1", "Le Pas Pressé",
     "A quicker step for numbers that float: an add now takes two clocks and a multiply three, where they took three and four, and the fused multiply-add keeps four, "
     "the latencies of Lion Cove and Zen 5. Ray tracing in hard float, run whole from reset, finds 4.020 primary rays per thousand clocks where it found 3.736, "
     "and 367.9 paths per million clocks where it found 326.6, in simulation; Dhrystone and 7-Zip clocks do not move.",
     dict(fp_lat=True, marks=["add in two, multiply in three"])),
    ("0.17.2", "La Racine",
     "Division and the square root at Lion Cove's pace: a single-precision divide in 7 clocks and a double in 10, roots in 10 and 15, where they took 11, 13, 12 and 18, "
     "and a new single divide may start every second clock. Paths per million clocks rise from 367.9 to 394.6 and primary rays from 4.020 to 4.136 per thousand, "
     "in simulation; Dhrystone and 7-Zip clocks do not move.",
     dict(fp_div=True, marks=["divide and root at Lion Cove's pace"])),
    # Figures from the 0.17.3 and 0.17.4 history rows; no drawing change, so the spec is the 0.17.2 spec.
    ("0.17.3", "Le Balai",
     "A sweep with no change in behaviour: the queue's index width now follows the queue's size, and the divider's dead state is removed. "
     "Dhrystone and the scaled 7-Zip kernel take the same clocks as before, with and without the floating-point unit.",
     dict(marks=["cleanup, bit-exact"])),
    ("0.17.4", "Le Créneau Libre",
     "A squashed divide or root no longer holds the divider's start interval: the next divide may begin as soon as the squashed one is gone. "
     "Dhrystone and 7-Zip are unchanged; the ray-tracing deltas are fractions of a percent, a model-correctness fix rather than a speed-up.",
     dict(marks=["a squashed divide frees the unit"])),
    # Figures from the 0.18.0 history row. The vector unit is an option off by default and not drawn.
    ("0.18.0", "Les Vecteurs",
     "Vectors arrive as an option of the out-of-order core, behind the floating-point switch: a subset of the RISC-V vector extension at 128, 256 or 512 bits, "
     "with unit-stride, strided and whole-register memory, element-precise faults, and every single-precision vector instruction of the contract. "
     "Dhrystone and 7-Zip clocks equal the baseline, with and without the unit; no performance claim is made.",
     dict(marks=["RVV subset, option off by default", "vector memory with element-precise faults"])),
    # Figures from the 0.19.0 history row. The wider lines are an option off by default, so the drawing adds a mark only.
    ("0.19.0", "Les Lignes",
     "Data-cache lines of 16, 32 or 64 bytes, as an option; the default 8-byte line and its clocks are unchanged. "
     "On the candidate, Dhrystone runs 15,669 to 15,644 clocks at 64-byte lines (4 KiB caches, four misses in flight); "
     "with the 7-Zip d12 kernel at slow memory (MEM_LAT 350), decompression falls 2.2% and compression rises 0.65%, a regression not yet explained.",
     dict(marks=["wider data-cache lines, option off by default"])),
    # Figures from the 0.19.1 history row. A new room: the predictor is a different subject from the lines of 0.19.0.
    ("0.19.1", "Le Présage",
     "An oracle for indirect jumps, as an option: targets that are not returns are guessed at fetch from five tagged tables of 512 entries over the branch target buffer, "
     "with a 128-bit path history. Off, the core is identical to 0.19.0. On the frontend's flat probe, 49.8 to 37.3 million clocks (-25.2%); "
     "Dhrystone and 7-Zip take the same clocks as before, and no hardware cost or timing is claimed.",
     dict(marks=["indirect-jump predictor, option off by default", "five tagged tables over the target buffer"])),
    # Figures from the 0.19.2 history row. A patch: the drawing is the same room as 0.19.1, with the delay path widened.
    ("0.19.2", "Le Seuil",
     "A repair in the memory system, not a new room: the sample SoC's DRAM and L2 delays are 64 bits end to end. Before, a backlog of 2^31 clocks or more "
     "wrapped and answered early. Below 2^31 clocks the results are bit-exact with 0.19.1; no speed, hardware cost or timing is claimed.",
     dict()),
]

ERAS = [
    ("I", "Salle I", "Les Premiers Pas", "One instruction at a time: a multicycle core finds its memory.", "0.1.0", "0.4.0"),
    ("II", "Salle II", "Le Duo et le Trio", "Two, then three instructions in the same clock.", "0.5.0", "0.7.1"),
    ("III", "Salle III", "La Chaîne", "The same contract, drawn again as a pipeline.", "0.8.0", "0.8.1"),
    ("IV", "Salle IV", "Le Désordre", "Out of order: instructions run when ready, retire in order.", "0.9.0", "0.9.4"),
    ("V", "Salle V", "L'Octuple", "Eight wide, and learning to guess.", "0.10.0", "0.11.2"),
    ("VI", "Salle VI", "Le Grand Format", "Sixteen wide, and then a council of engineers.", "0.12.0", "0.13.0"),
    ("VII", "Salle VII", "Le Conseil", "The council widens everything at once: doors, room and breath, then a mending, a deeper memory for returns, and a fourth hand for branches.", "0.13.1", "0.14.6"),
    ("VIII", "Salle VIII", "L'Archive", "The council turns to a second measure, the LZMA kernel of 7-Zip: a quicker multiply, honest offsets, a mended way home, floors of memory below, and a predictor with a long memory.", "0.14.7", "0.15.2"),
    ("IX", "Salle IX", "Les Lettres en Vol", "Mendings for the branch buffer, a near memory and a ledger of waiting loads, six tables of long memory, then several reads in flight at once, a weld that spans two clocks, and loads that sleep until their answer comes.", "0.15.3", "0.16.2"),
    ("X", "Salle X", "La Virgule Flottante", "Numbers that float: single and double precision arrive in the out-of-order core, built in only on request, then add, multiply, divide and root at the latencies of Lion Cove and Zen 5.", "0.17.0", "0.17.4"),
    ("XI", "Salle XI", "Les Vecteurs", "Vectors as an option: a first subset of the RISC-V vector extension, executed in order at the head of the reorder buffer, with the rest of the instructions still to come.", "0.18.0", "0.18.0"),
    ("XII", "Salle XII", "Les Lignes", "Wider lines for the data cache, as an option: a miss fills a longer line, answered one beat at a time, the critical beat first.", "0.19.0", "0.19.0"),
    ("XIII", "Salle XIII", "Le Présage", "A guess for every indirect jump, as an option: the target of a jump that is not a return is predicted at fetch from tagged tables that remember the path taken.", "0.19.1", "0.19.1"),
]


def build_specs() -> list[dict]:
    specs, cur = [], dict(DEFAULTS)
    for ver, title, cap, ov in WORKS:
        nxt = dict(cur)
        for k, v in ov.items():
            if k == "marks":
                nxt["marks"] = list(cur["marks"]) + v
            else:
                nxt[k] = v
        nxt["version"], nxt["title"], nxt["caption"] = ver, title, cap
        specs.append(nxt)
        cur = nxt
    return specs


def unit_lines(s: dict) -> list[tuple[str, str]]:
    """Human-readable unit list: only values the sources give; the rest is qualitative."""
    u = []
    if s["kind"] == "mc":
        u.append(("Organisation", "Multicycle core (rtl/cpu/rv64_core.sv)"))
        u.append(("Control states", ", ".join(s["states"]).title().replace(", ", " · ")))
        u.append(("Issue", f"{s['issue']} per clock"))
        u.append(("Retirement", f"{s['retire']} per clock"))
        if s["fetch_buf"]:
            u.append(("Fetch", "one-beat fetch buffer (8 bytes)"))
        if s["icache_kb"]:
            u.append(("Instruction cache", f"{s['icache_kb']} KiB, direct-mapped, 8-byte lines"))
        if s["dcache_kb"]:
            u.append(("Data cache", f"{s['dcache_kb']} KiB, direct-mapped, write-through"))
        if s["slot2"]:
            u.append(("Second slot", ", ".join(s["slot2"])))
        if s["folding"]:
            u.append(("Branch folding", "yes"))
        if s["mul"]:
            u.append(("Multiply / divide", "M extension; divide one step per clock"))
        if s["bext"]:
            u.append(("Bit manipulation", "Zba, Zbb, Zbs"))
    elif s["kind"] == "pipe":
        u.append(("Organisation", "Pipelined, single issue (rtl/cpu/rv64_pipe.sv)"))
        u.append(("Stages", " · ".join(s["stages"])))
        u.append(("Branch target buffer", f"{s['btb']} entries"))
        u.append(("Return stack", f"{s['ras']} entries"))
        u.append(("Caches", "4 KiB each, block-RAM style"))
        if s["fq"]:
            u.append(("Fetch queue", "between F and D"))
        u.append(("Retirement", "1 per clock"))
    else:
        u.append(("Organisation", "Out of order (rtl/cpu/rv64_ooo.sv)"))
        u.append(("Fetch / rename / retire", f"{s['fetch_w']} / {s['decode_w']} / {s['retire']} per clock"))
        u.append(("Reorder buffer", f"{s['rob']} entries"))
        u.append(("Physical registers", str(s["prf"])))
        u.append(("Issue queue", f"{s['iq']} entries"))
        if s["full"]:
            u.append(("ALUs", f"{s['alus']}, of which {s['full']} full (branch, multiply, divide)"))
        else:
            u.append(("Integer ports", str(s["alus"])))
        if s["ldst_shared"]:
            u.append(("Memory port", "one load/store port, memory issued in program order"))
        else:
            u.append(("Memory ports", f"{s['loads']} load, {s['stores']} store-address"))
        btb = f"{s['btb_n']:,} entries, with return stack"
        if s["btb_guard"]:
            btb += "; hits used only for branch, JAL and JALR"
        if s["btb_rel"]:
            btb += "; targets as signed PC-relative offsets (±2 GiB)"
        u.append(("Branch target buffer", btb))
        u.append(("Caches", f"{s['icache_kb'] or 4} KiB instruction, {s['dcache_kb'] or 4} KiB data"
                  + (", two-way data cache" if s["dc_ways"] == 2 else "")))
        if s["taken"]:
            u.append(("Taken transfers per fetch", str(s["taken"])))
        if s["loop"]:
            u.append(("Loop predictor", f"{s['lp_n']:,} entries"))
        if s["bias"]:
            u.append(("Branch bias", "a branch that has gone one way at least 4 times with no exit is predicted that way"))
        if s["fuse"]:
            u.append(("Instruction fusion", "a simple integer producer and the next instruction reading it"
                      + (", also across rename groups (one pending producer held into the next clock)" if s["fuse_x"] else "")))
        if s["paired"]:
            u.append(("Store writes", "paired on the bus"))
        if s["vp"]:
            u.append(("Value prediction", "loads, multiplies, divides"))
        if s["predecode"]:
            u.append(("Fetch predecode", "direct jumps, calls, returns, backward branches"))
        if s["tage"] and s["tg_n"] == 6:
            u.append(("Global-history predictor", "6 tagged tables, histories 4 to 128, about 22.4 KiB in all; aging covers every entry"))
        elif s["tage"]:
            u.append(("Global-history predictor", "4 × 1,024 tagged entries, histories 5 / 15 / 44 / 128, about 18.4 KiB"))
        if s["vp_conf"]:
            u.append(("Prediction confidence", "32 equal results to predict, doubled per wrong prediction up to 64"))
        if s["mul_lat"]:
            u.append(("Multiply latency", f"{s['mul_lat']} clocks (behavioural; DSP timing unproven)"))
        if s["ld_knob"]:
            u.append(("Load-to-use latency", "a knob, RV64_OOO_LD_LAT, default 1 clock"))
        if s["l2"]:
            u.append(("Memory hierarchy", "optional SoC L2 and memory latency (L2_KIB, L2_WAYS, L2_LINE, L2_LAT, MEM_LAT); defaults keep timing"))
        if s["l0"]:
            u.append(("Recent-beat buffer", "a knob, RV64_OOO_L0_N (default 0, off), latency RV64_OOO_L0_LAT (default 2)"))
        if s["ldwait"]:
            u.append(("Load-wait table", "4,096 entries, cleared every 65,536 clocks"))
        if s["n_miss"]:
            u.append(("Data misses in flight", "N_MISS 1 to 8 (default 1); split reads with tags on mem_tag, rsp_valid, rsp_tag, rsp_data, rsp_error"
                      + ("; younger missed loads sleep until their beat's answer (wake on fill)" if s["wake_fill"] else "")))
        if s["fpu"]:
            u.append(("Floating point", "RV64F and RV64D behind the define RV64_OOO_FPU, default off: four FP ports (two FMA, two misc), "
                      "pipelined divide and square root, a 64-entry rename map (x and f) on one physical register file, fflags at retirement"))
            if s["fp_lat"] or s["fp_div"]:
                lat = ["add 2, multiply 3, fused multiply-add 4" if s["fp_lat"] else "add 3, multiply 4, fused multiply-add 4"]
                if s["fp_div"]:
                    lat.append("divide 7 / 10 and square root 10 / 15 (single / double), a single divide every 2 clocks")
                u.append(("FP latencies, clocks", "; ".join(lat)))
    return u


# ---------------------------------------------------------------------------
# SVG artwork
# ---------------------------------------------------------------------------

W, H = 800, 1000


class Art:
    def __init__(self, spec: dict):
        self.s = spec
        self.rng = random.Random("rv64-" + spec["version"])
        self.back: list[str] = []
        self.parts: list[str] = []

    # primitives -----------------------------------------------------------
    def a(self, x: str):
        self.parts.append(x)

    def box(self, x, y, w, h, fill=None, sw=2.0, dash=None, op=1.0, off=3.0, rx=0):
        if fill:
            self.a(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}" fill-opacity="{op}"/>')
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.a(f'<rect x="{x - off * (1 if fill else 0):.1f}" y="{y - off * (1 if fill else 0):.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="none" stroke="{INK}" stroke-width="{sw}"{d}/>')

    def disc(self, cx, cy, r, fill=None, sw=2.0, op=1.0, off=2.5, dash=None):
        if fill:
            self.a(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" fill-opacity="{op}"/>')
        d = f' stroke-dasharray="{dash}"' if dash else ""
        o = off if fill else 0
        self.a(f'<circle cx="{cx - o:.1f}" cy="{cy - o:.1f}" r="{r:.1f}" fill="none" stroke="{INK}" stroke-width="{sw}"{d}/>')

    def line(self, x1, y1, x2, y2, sw=1.4, col=INK, op=1.0, dash=None, g=False):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        (self.back if g else self.parts).append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{col}" stroke-width="{sw}" stroke-opacity="{op}"{d} stroke-linecap="round"/>')

    def path(self, d, sw=1.6, col=INK, fill="none", op=1.0, dash=None):
        dd = f' stroke-dasharray="{dash}"' if dash else ""
        self.a(f'<path d="{d}" fill="{fill}" stroke="{col}" stroke-width="{sw}" stroke-opacity="{op}"{dd} stroke-linecap="round" stroke-linejoin="round"/>')

    def arc(self, cx, cy, r, a0, a1, col, sw=26, op=0.95):
        x0, y0 = cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0))
        x1, y1 = cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1))
        large = 1 if (a1 - a0) % 360 > 180 else 0
        self.a(f'<path d="M{x0:.1f} {y0:.1f} A{r} {r} 0 {large} 1 {x1:.1f} {y1:.1f}" fill="none" stroke="{col}" stroke-width="{sw}" stroke-opacity="{op}"/>')
        for rr in (r - sw / 2, r + sw / 2):
            xa, ya = cx + rr * math.cos(math.radians(a0)), cy + rr * math.sin(math.radians(a0))
            xb, yb = cx + rr * math.cos(math.radians(a1)), cy + rr * math.sin(math.radians(a1))
            self.a(f'<path d="M{xa:.1f} {ya:.1f} A{rr:.1f} {rr:.1f} 0 {large} 1 {xb:.1f} {yb:.1f}" fill="none" stroke="{INK}" stroke-width="1.4"/>')

    def text(self, x, y, t, size=18, anchor="middle", col=INK, italic=True, op=1.0):
        st = "italic" if italic else "normal"
        self.a(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-family="Cormorant Garamond, Georgia, serif" font-size="{size}" font-style="{st}" fill="{col}" fill-opacity="{op}">{e(t)}</text>')

    def dots(self, x, y, cols, rows, pitch, r, fill, first_off=None):
        for j in range(rows):
            for i in range(cols):
                self.a(f'<circle cx="{x + i * pitch:.1f}" cy="{y + j * pitch:.1f}" r="{r}" fill="{fill}" stroke="{INK}" stroke-width="0.8"/>')

    # composition ----------------------------------------------------------
    def complexity(self) -> int:
        s = self.s
        c = 3 + s["issue"] + s["retire"] + len(s["marks"]) + (s["rob"] // 16) + (s["alus"] // 2)
        c += 2 * (s["kind"] != "mc") + (s["icache_kb"] is not None) + (s["dcache_kb"] is not None)
        return c

    def air(self):
        """Kandinsky-like free marks behind the plan; more of them as the machine grows."""
        n = 2 + self.complexity() // 3
        cols = [OCHRE, OXBLOOD, SLATE, SAGE, GOLD]
        r = self.rng
        # blueprint grid
        for x in range(60, W, 40):
            self.line(x, 40, x, H - 40, sw=0.5, col=SLATE, op=0.10, g=True)
        for y in range(40, H - 39, 40):
            self.line(60, y, W - 60, y, sw=0.5, col=SLATE, op=0.10, g=True)
        for i in range(n):
            t = r.random()
            c = cols[r.randrange(len(cols))]
            if t < 0.4:
                self.back.append(f'<circle cx="{r.uniform(80, 720):.0f}" cy="{r.uniform(60, 940):.0f}" r="{r.uniform(10, 70):.0f}" fill="none" stroke="{c}" stroke-width="{r.uniform(0.8, 2):.1f}" stroke-opacity="0.55"/>')
            elif t < 0.75:
                x, y = r.uniform(60, 740), r.uniform(60, 940)
                a = math.radians(r.choice([-35, -20, 15, 30, 60, 75]))
                L = r.uniform(60, 200)
                self.line(x, y, x + L * math.cos(a), y + L * math.sin(a), sw=r.uniform(0.8, 2), col=c, op=0.5, g=True)
            else:
                self.back.append(f'<circle cx="{r.uniform(80, 720):.0f}" cy="{r.uniform(60, 940):.0f}" r="{r.uniform(3, 8):.0f}" fill="{c}" fill-opacity="0.7"/>')

    def predictor(self, cx, cy):
        s = self.s
        if not s["btb"]:
            return
        rings = max(int(math.log2(s["btb_n"])) - 4, 4) if s["kind"] == "ooo" else 4  # 256 entries: 4 rings; 1,024: 6 finer rings
        for i in range(rings):
            self.a(f'<circle cx="{cx}" cy="{cy}" r="{56 * (i + 1) / rings:.1f}" fill="none" stroke="{INK}" stroke-width="{1.6 if i % 2 == 0 else 0.8}"/>')
        self.disc(cx, cy, 9, OXBLOOD, off=2)
        if s["tage"]:
            # tagged tables as arcs around the rings; each arc's sweep follows its history
            # length (5, 15, 44, 128 for four tables; 4 to 128 by doubling for six, the RTL's
            # tg_len at cpu-v0.15.7), so the longest memory nearly closes the circle
            if s["tg_n"] == 6:
                hists, cols, step = (4, 8, 16, 32, 64, 128), (OCHRE, OXBLOOD, SLATE, SAGE, GOLD, OXBLOOD), 5
            else:
                hists, cols, step = (5, 15, 44, 128), (OCHRE, OXBLOOD, SLATE, SAGE), 7
            for i, (hist, col) in enumerate(zip(hists, cols)):
                sweep = 40 + 270 * hist / 128
                self.arc(cx, cy, 64 + i * step, 150, 150 + sweep, col, sw=4, op=0.9)
        if s["ras"]:
            for i in range(4):
                self.box(cx - 30 + i * 4, cy + 74 - i * 7, 60, 6, SAGE, sw=1, off=0)
        if s["loop"]:
            pts = []
            for i in range(0, 260, 12):
                rr = 4 + i * 0.07
                pts.append(f"{cx + 78 + rr * math.cos(math.radians(i)):.1f},{cy + 12 + rr * math.sin(math.radians(i)):.1f}")
            self.path("M" + " L".join(pts), sw=1.8, col=GOLD)
        if s["predecode"]:
            self.line(cx + 60, cy + 40, cx + 130, cy - 6, sw=3, col=GOLD)
        if s["btb_guard"]:
            # a small gate across the predictor's way out: only transfers pass
            self.line(cx - 6, cy - 62, cx + 6, cy - 50, sw=2.2, col=OXBLOOD)
            self.line(cx + 6, cy - 62, cx - 6, cy - 50, sw=2.2, col=OXBLOOD)
        if s["btb_rel"]:
            # a measured distance from the centre: targets kept relative to the branch
            self.line(cx, cy, cx - 50, cy + 30, sw=1.2, col=INK, dash="2 3")
            self.disc(cx - 50, cy + 30, 3.2, GOLD, off=0)

    def retire_col(self, y0, y1, x=725):
        n = self.s["retire"]
        self.line(x, y0 - 14, x, y1 + 14, sw=2.2, col=GOLD)
        step = (y1 - y0) / max(n, 1)
        rad = min(10, step / 2 - 1)
        for i in range(n):
            self.disc(x, y0 + step * (i + 0.5), rad, GOLD, off=min(2, rad / 4))
        self.text(x, y1 + 40, "retire", 17, col=INK, op=0.7)

    def marks(self):
        ms = self.s["marks"]
        # one gold diamond per mark, right-aligned clear of the predictor (x >= 220);
        # past 28 marks they hang in two rows, closer together if need be
        n = len(ms)
        per_row = n if n <= 28 else math.ceil(n / 2)
        pitch = min(18, 520 / max(per_row, 1))
        rows = [ms[:n - per_row], ms[n - per_row:]] if n > per_row else [ms]
        for r, row in enumerate(reversed(rows)):
            y = 50 - 16 * r
            x0 = W - 60 - pitch * len(row)
            for i, _ in enumerate(row):
                x = x0 + pitch * i + pitch / 2
                self.a(f'<path d="M{x:.1f} {y} l7 7 l-7 7 l-7 -7z" fill="{GOLD}" stroke="{INK}" stroke-width="1"/>')

    def caches(self, top):
        s = self.s
        ic, dc = s["icache_kb"], s["dcache_kb"]

        def side(kb):
            return 80 + 20 * math.log2(kb)
        if ic or s["kind"] != "mc":
            kb = ic or 4
            w = side(kb)
            self.box(70, top, w, w * 0.62, SLATE, op=0.85)
            self.line(70, top + w * 0.31, 70 + w, top + w * 0.31, sw=0.8)
            for i in range(1, int(w // 20)):
                self.line(70 + i * 20, top, 70 + i * 20, top + w * 0.62, sw=0.6, op=0.6)
            self.text(70 + w / 2, top + w * 0.62 + 24, "instructions", 18, op=0.8)
        if dc or s["kind"] != "mc":
            kb = dc or 4
            w = side(kb)
            x = 730 - w
            h = w * 0.62
            self.box(x, top, w, h, OCHRE, op=0.85)
            if s["dc_ways"] == 2:
                self.line(x + w / 2, top, x + w / 2, top + h, sw=2.2)
                self.box(x + w / 2, top, w / 2, h, OXBLOOD, op=0.45, off=0)
            for i in range(1, int(w // 20)):
                self.line(x + i * 20, top, x + i * 20, top + h, sw=0.6, op=0.5)
            self.text(x + w / 2, top + h + 24, "data", 18, op=0.8)
        if s["kind"] == "mc" and not ic and s["fetch_buf"]:
            self.box(70, top + 20, 70, 38, SLATE, op=0.7)
            self.text(105, top + 80, "buffer", 18, op=0.8)

    def bus(self, y):
        lanes = 2 if self.s["paired"] else 1
        for i in range(lanes):
            self.line(60, y + i * 12, 740, y + i * 12, sw=5 if i == 0 else 3, col=INK)
        self.a(f'<rect x="60" y="{y - 14}" width="680" height="{14 + 12 * lanes + 4}" fill="none"/>')
        self.text(400, y + 12 * lanes + 36, "the bus", 18, op=0.7)

    # families -------------------------------------------------------------
    def lane_geometry(self, n):
        """(box width, gap, first x): the 16-lane rows start right of the predictor."""
        if n > 8:
            gap = 3
            w = (530 - gap * (n - 1)) / n
            return w, gap, 215
        return 42, 6, 400 - (n * 48 - 6) / 2

    def fetch_row(self, y, n, dashed=False):
        w, gap, x0 = self.lane_geometry(n)
        tot = n * (w + gap) - gap
        if n <= 8:
            x0 = 400 - tot / 2
        for i in range(n):
            self.box(x0 + i * (w + gap), y, w, 34, OCHRE, dash="5 3" if dashed else None)
        return x0, tot

    def multicycle(self):
        s = self.s
        fx0, ft = self.fetch_row(96, s["fetch_w"], dashed=(not s["fetch_buf"] and not s["icache_kb"]))
        self.text(400, 86, "fetch", 18, op=0.8)
        if s["fetch_buf"]:
            self.box(fx0 + ft + 24, 100, 34, 26, SLATE, op=0.8)
        # the ring of control states
        cx, cy, r = 400, 410, 128
        n = len(s["states"])
        cmap = {"FETCH": OCHRE, "EXECUTE": SLATE, "MEMORY": OXBLOOD, "DIVIDE": SAGE, "MULTIPLY": GOLD}
        span = 360 / n
        for i, st in enumerate(s["states"]):
            a0 = -90 + i * span + 5
            a1 = -90 + (i + 1) * span - 5
            self.arc(cx, cy, r, a0, a1, cmap[st])
            am = math.radians((a0 + a1) / 2)
            self.text(cx + (r + 38) * math.cos(am), cy + (r + 38) * math.sin(am) + 5, st.lower(), 17, op=0.8)
        # register file x0..x31: 4 rows of 8
        for j in range(4):
            for i in range(8):
                fill = INK if (i == 0 and j == 0) else SAGE
                self.box(cx - 76 + i * 20, cy - 40 + j * 20, 15, 15, fill, sw=1, off=0.8)
        self.text(cx, cy + 62, "32 × 64", 16, op=0.7)
        self.line(400, 134, 400, cy - r - 14, sw=1.6)
        # issue slots / ALUs
        k = s["issue"]
        ys = 640
        xs = [400 + (i - (k - 1) / 2) * 120 for i in range(k)]
        for i, x in enumerate(xs):
            self.disc(x, ys, 36 if i == 0 else 30, SLATE if i == 0 else OCHRE, op=0.9)
            self.line(x, cy + r + 20, x, ys - 40, sw=1.2, op=0.7)
            if i == 0 or i == 1:
                pass
        if s["bext"]:
            for i in range(8):
                self.box(xs[0] - 44 + i * 11, ys - 66, 9, 14, INK if i % 3 != 1 else PAPER, sw=0.8, off=0)
        for c, cap in enumerate(s["slot2"]):
            if k > 1:
                self.a(f'<path d="M{xs[1] - 14 + 9 * c} {ys + 44} l5 -9 l5 9z" fill="{GOLD}" stroke="{INK}" stroke-width="0.8"/>')
        if s["folding"] and k > 1:
            self.path(f"M{xs[0] + 36} {ys} Q{(xs[0] + xs[1]) / 2} {ys - 70} {xs[1] - 30} {ys}", sw=2.2, col=OXBLOOD)
        if s["mul"]:
            mx = 640 if k < 3 else 700
            mx = 120 if k >= 3 else 130
            self.box(mx - 28, ys - 28, 56, 56, SAGE)
            self.line(mx - 18, ys - 18, mx + 18, ys + 18, sw=2.4)
            self.line(mx + 18, ys - 18, mx - 18, ys + 18, sw=2.4)
            self.line(mx, ys - 28, mx, ys - 12, sw=0.01)
            if s["div"]:
                self.disc(mx, ys + 84, 20, SAGE)
                self.line(mx - 12, ys + 84, mx + 12, ys + 84, sw=2.4)
                self.disc(mx, ys + 76, 2.5, INK, off=0)
                self.disc(mx, ys + 92, 2.5, INK, off=0)
        self.retire_col(320, 520)
        # memory port to bus
        if s["issue"] >= 1:
            self.line(xs[0], ys + 40, xs[0], 780, sw=1.2, op=0.7)
        self.caches(792)
        self.bus(935)
        self.retire_wire = None

    def pipeline(self):
        s = self.s
        self.fetch_row(96, 1)
        self.text(400, 86, "fetch", 18, op=0.8)
        self.predictor(130, 140)
        self.path("M372 112 C300 70 200 80 150 108", sw=1.8, col=GOLD)
        st = s["stages"]
        cols = [OCHRE, OXBLOOD, SLATE, SAGE, GOLD]
        hs = [210, 250, 190, 230, 150]
        n = len(st)
        wsl = 96
        gap = 18
        tot = n * wsl + (n - 1) * gap
        x0 = 400 - tot / 2
        for i, nm in enumerate(st):
            x = x0 + i * (wsl + gap)
            y = 220 + (i % 2) * 22
            self.box(x, y, wsl, hs[i], cols[i], op=0.9)
            self.text(x + wsl / 2, y + hs[i] / 2 + 22, nm, 66, col=PAPER, op=0.95)
            if i:
                self.line(x - gap, y + 40, x, y + 40, sw=1.6)
            if nm == "D":
                self.dots(x + 14, y + hs[i] + 18, 8, 4, 10.5, 3.2, SAGE)
        if s["fq"]:
            fx = x0 + wsl + 3
            for k in range(4):
                self.box(fx + 2, 240 + k * 14, gap - 6, 11, GOLD, sw=1, off=0)
        # ALU and multiplier under E
        ex = x0 + 2 * (wsl + gap) + wsl / 2
        self.disc(ex, 600, 38, SLATE, op=0.9)
        self.line(ex, 220 + 22 * 0 + hs[2] + 0, ex, 560, sw=1.2, op=0.7)
        self.box(ex + 70, 572, 52, 52, SAGE)
        self.line(ex + 78, 580, ex + 114, 616, sw=2.2)
        self.line(ex + 114, 580, ex + 78, 616, sw=2.2)
        self.retire_col(320, 520)
        self.line(400, 134, 400, 220, sw=1.4)
        mx = x0 + 3 * (wsl + gap) + wsl / 2
        self.line(mx, 220 + 22 + hs[3], mx, 780, sw=1.2, op=0.7)
        self.caches(792)
        self.bus(935)

    def ooo(self):
        s = self.s
        fx0, ft = self.fetch_row(96, s["fetch_w"])
        self.text(400, 86, "fetch" if s["fetch_w"] <= 8 else f"fetch, {s['fetch_w']} lanes", 18, op=0.8)
        self.predictor(120, 136)
        for t in range(max(s["taken"], 1)):
            self.path(f"M{fx0 + 6} {100 + t * 4} C{fx0 - 40} {60 - t * 14} 200 {58 - t * 14} 150 {104 + t * 6}",
                      sw=1.8, col=GOLD)
        # rename row, slot by slot under fetch
        n = s["decode_w"]
        dw, dg, dx0 = self.lane_geometry(n)
        dp = dw + dg
        for i in range(n):
            self.box(dx0 + i * dp, 178, dw, 28, OXBLOOD, op=0.85)
            self.line(dx0 + i * dp + dw / 2, 130, dx0 + i * dp + dw / 2, 178, sw=0.9, op=0.7)
            self.a(f'<line x1="{dx0 + i * dp + dw * 0.15:.1f}" y1="200" x2="{dx0 + i * dp + dw * 0.85:.1f}" y2="184" stroke="{INK}" stroke-width="0.8" stroke-opacity="0.6"/>')
        self.text(400, 232, "rename", 18, op=0.8)
        if s["fuse_x"]:
            # one held-over producer: a gold register under the last rename slot, hooked back
            # to the first slot of the next clock's group
            lx = dx0 + (n - 1) * dp + dw / 2
            self.box(lx - 9, 214, 18, 11, GOLD, sw=1.2, off=1)
            self.path(f"M{lx - 10} 222 C{lx - 60} 252 {dx0 + 60} 252 {dx0 + dw / 2} 210", sw=1.4, col=GOLD, dash="4 3")
        if s["snapshots"]:
            self.box(dx0 - 10, 170, n * dp + 14, 44, None, sw=1.2, dash="3 4", off=0)
        # window: reorder buffer, register file, issue queue
        cell = 14
        rcell = 14 if s["rob"] <= 128 else 10
        cols = 4 if s["rob"] <= 32 else (8 if s["rob"] <= 128 else 16)
        rows = s["rob"] // cols
        rx, ry = 70, 276
        for j in range(rows):
            for i in range(cols):
                self.a(f'<rect x="{rx + i * rcell}" y="{ry + j * rcell}" width="{rcell - 2}" height="{rcell - 2}" fill="{OXBLOOD}" fill-opacity="{0.35 + 0.5 * ((i + j) % 3) / 2:.2f}" stroke="{INK}" stroke-width="0.7"/>')
        self.text(rx + cols * rcell / 2, ry + rows * rcell + 22, f"{s['rob']} in order", 17, op=0.8)
        pcols = 8 if s["prf"] <= 64 else 16
        prow = math.ceil(s["prf"] / pcols)
        px = (330 if s["rob"] <= 128 else 345) - (pcols * 10) / 2
        py = 290
        for k in range(s["prf"]):
            i, j = k % pcols, k // pcols
            fill = INK if k < 32 else (GOLD if s["fpu"] and k < 64 else SAGE)
            self.a(f'<circle cx="{px + i * 10 + 5:.0f}" cy="{py + j * 10 + 5:.0f}" r="3.4" fill="{fill}" stroke="{INK}" stroke-width="0.6"/>')
        self.text(px + pcols * 5, py + prow * 10 + 24, f"{s['prf']} names", 17, op=0.8)
        icell = 14 if s["iq"] <= 64 else 10
        icols = 8 if s["iq"] <= 64 else 16
        irows = max(s["iq"] // icols, 1)
        ix = 520
        iy = 290
        self.path(f"M{ix - 6} {iy - 16} L{ix + icols * icell + 4} {iy - 16} L{ix + icols * icell / 2 - 2} {iy - 2}Z", sw=1.4, fill=SLATE, op=0.9)
        for j in range(irows):
            for i in range(icols):
                self.box(ix + i * icell, iy + j * icell, icell - 2, icell - 2, SLATE, op=0.75, sw=0.8, off=0)
        self.text(ix + icols * icell / 2, iy + irows * icell + 22, f"{s['iq']} waiting", 17, op=0.8)
        if s["fq"] or s["fetch_w"] > 1:
            pass
        self.line(400, 206, 400, 262, sw=1.2, op=0.7)
        self.line(400, 262, rx + cols * rcell / 2, 262, sw=1.2, op=0.7)
        self.line(400, 262, ix + icols * icell / 2, 262, sw=1.2, op=0.7)
        self.retire_col(300, 500)
        self.line(rx + cols * rcell, ry + 40, 700, ry + 40, sw=0.9, col=GOLD, op=0.9)
        # execution row
        k = s["alus"]
        pitch = min(78, 600 / max(k, 1))
        y = 600
        xs = [400 + (i - (k - 1) / 2) * pitch for i in range(k)]
        fullset = set(range(s["full"]))
        rad = 28 if k <= 4 else 26
        for i, x in enumerate(xs):
            full = i in fullset
            self.line(ix + icols * icell / 2, iy + irows * icell + 36, x, y - rad - 6, sw=0.9, op=0.6)
            self.disc(x, y, rad, SLATE if not full else OXBLOOD, op=0.9)
            if full:
                self.disc(x, y, rad + 8, None, sw=1.2)
        if s["fuse"] and k > 2:
            # a gold clasp joining two neighbouring units: producer and consumer as one
            self.path(f"M{xs[1] + 4} {y - rad - 14} Q{(xs[1] + xs[2]) / 2} {y - rad - 44} {xs[2] - 4} {y - rad - 14}", sw=2.6, col=GOLD)
            self.disc(xs[1] + 4, y - rad - 14, 3.5, GOLD, off=0)
            self.disc(xs[2] - 4, y - rad - 14, 3.5, GOLD, off=0)
        # memory ports
        ly = 722
        if s["ldst_shared"]:
            xsm = [600]
            self.a(f'<path d="M{600 - 34} {ly} a34 34 0 0 1 68 0z" fill="{OCHRE}" stroke="{INK}" stroke-width="2"/>')
            self.line(600, ly, 600, 780, sw=1.2, op=0.7)
        else:
            lx = [180 + 70 * i for i in range(s["loads"])]
            sx = [560 + 70 * i for i in range(s["stores"])]
            for x in lx:
                self.a(f'<path d="M{x - 30} {ly} a30 30 0 0 1 60 0z" fill="{OCHRE}" stroke="{INK}" stroke-width="2"/>')
                self.line(x, ly, x, 780, sw=1.2, op=0.7)
                if s["vp"]:
                    self.a(f'<circle cx="{x}" cy="{ly}" r="44" fill="none" stroke="{GOLD}" stroke-width="2" stroke-dasharray="2 5"/>')
            for x in sx:
                self.a(f'<path d="M{x - 30} {ly} a30 30 0 0 0 60 0z" fill="{OXBLOOD}" stroke="{INK}" stroke-width="2"/>')
            if s["vp"]:
                self.a(f'<circle cx="{xs[0]}" cy="{y}" r="42" fill="none" stroke="{GOLD}" stroke-width="2" stroke-dasharray="2 5"/>')
        if s["vp"] and s["ldst_shared"]:
            pass
        if s["fwd"]:
            mid = 600 if s["ldst_shared"] else 470
            self.path(f"M{mid - 70} {ly + 18} C{mid - 40} {ly + 70} {mid + 40} {ly + 70} {mid + 70} {ly + 18}", sw=2, col=GOLD)
            self.a(f'<path d="M{mid + 70} {ly + 18} l-9 -4 l3 10z" fill="{GOLD}" stroke="{INK}" stroke-width="0.8"/>')
        if s["ld_knob"]:
            # the load-latency dial: a small gauge left of the load ports, needle at one clock
            self.disc(112, ly - 16, 18, PAPER, sw=1.6, off=0)
            for k in range(5):
                a = math.radians(200 + k * 35)
                self.line(112 + 13 * math.cos(a), ly - 16 + 13 * math.sin(a),
                          112 + 18 * math.cos(a), ly - 16 + 18 * math.sin(a), sw=1)
            a = math.radians(200)
            self.line(112, ly - 16, 112 + 15 * math.cos(a), ly - 16 + 15 * math.sin(a), sw=2, col=OXBLOOD)
        if s["l0"]:
            # the recent-beat buffer: sixteen small cells under the load ports, dashed
            # because the knob is off by default
            for k in range(16):
                self.box(142 + k * 10, 756, 8, 8, OCHRE, op=0.6, sw=0.8, dash="2 2", off=0)
        if s["ldwait"]:
            # the load-wait ledger: a grid of bits (symbolic for 4,096) beside a clock hand
            # that sweeps it clean every 65,536 clocks
            for j in range(4):
                for i in range(8):
                    on = (i * 7 + j * 3) % 5 == 0
                    self.box(592 + i * 9, 648 + j * 9, 7, 7, OXBLOOD if on else PAPER, op=0.8, sw=0.6, off=0)
            self.disc(700, 664, 13, None, sw=1.2)
            self.line(700, 664, 700, 653, sw=1.6, col=OXBLOOD)
            self.line(700, 664, 708, 668, sw=1.2)
        if s["n_miss"]:
            # up to eight reads in flight: entry 0 solid (the oldest load's), the rest dashed
            # (N_MISS defaults to 1); the split answer channel climbs back from the bus
            for k in range(8):
                self.box(560 + k * 21, 762, 16, 12, OXBLOOD if k == 0 else PAPER, op=0.85,
                         sw=1.1, dash=None if k == 0 else "3 2", off=0)
            self.path("M748 936 L748 768 L730 768", sw=1.6, col=OXBLOOD, dash="5 3")
            self.a(f'<path d="M730 768 l7 -4 l0 8z" fill="{OXBLOOD}" stroke="{INK}" stroke-width="0.8"/>')
            for k in range(4):
                self.line(744, 800 + k * 32, 752, 800 + k * 32, sw=1.2)
            if s["wake_fill"]:
                # wake on fill: the answer runs back along the slots and touches each sleeper
                self.path("M736 757 L578 757", sw=1.3, col=GOLD, dash="2 3")
                for k in range(1, 8):
                    self.disc(560 + k * 21 + 8, 757, 2.6, GOLD, sw=0.8, off=0)
        if s["fpu"]:
            # four floating-point ports, dashed because the define is off by default: two FMA
            # (oxblood centres) and two misc, the last notched for the pipelined divider;
            # the f registers are the gold row of the register file, and a gold flag on the
            # retire column is fflags settling at retirement
            fy = 668
            for i in range(4):
                fx = 452 + i * 34
                self.line(ix + icols * icell / 2, iy + irows * icell + 36, fx, fy - 15, sw=0.7, op=0.45, dash="3 3")
                self.disc(fx, fy, 13, SAGE, op=0.85, dash="3 2", sw=1.4, off=1.5)
                if i < 2:
                    self.disc(fx, fy, 6, OXBLOOD, sw=0.8, off=0)
            for k in range(6):
                a = math.radians(k * 60)
                self.line(554 + 9 * math.cos(a), fy + 9 * math.sin(a), 554 + 13 * math.cos(a), fy + 13 * math.sin(a), sw=1)
            self.line(725, 500, 725, 528, sw=1.2)
            self.path("M725 506 L745 511 L725 517 Z", sw=1, fill=GOLD)
            if s["fp_lat"]:
                # a quicker step: two gold beats under the first multiply-add port (add in two)
                # and three under the second (multiply in three)
                for i, n in ((0, 2), (1, 3)):
                    fx = 452 + i * 34
                    for k in range(n):
                        self.disc(fx - (n - 1) * 3.5 + k * 7, fy + 21, 2.2, GOLD, sw=0.7, off=0)
            if s["fp_div"]:
                # the divider's notches gain a gold radical: divide and root at Lion Cove's pace
                self.path(f"M547 {fy + 1} L550 {fy + 5} L554 {fy - 6} L561 {fy - 6}", sw=1.6, col=GOLD)
        self.caches(796)
        if s["l2"]:
            self.memory_floors(796)
        self.bus(940)

    def memory_floors(self, top):
        """The optional second level between the two caches, and the delay line to a distant memory.
        Dashed because the defaults leave both closed."""
        x0, x1 = 312, 488
        self.box(x0, top + 6, x1 - x0, 70, SAGE, op=0.55, dash="6 4", sw=1.8)
        for i in range(1, 8):
            self.line(x0 + i * (x1 - x0) / 8, top + 6, x0 + i * (x1 - x0) / 8, top + 76, sw=0.6, op=0.5)
        self.text(400, top + 47, "second level", 17, op=0.85)
        # each first-level cache reaches the second level
        self.line(296, top + 40, x0 - 4, top + 40, sw=1.2, op=0.7, dash="3 3")
        self.line(x1, top + 40, 504, top + 40, sw=1.2, op=0.7, dash="3 3")
        # the long walk to memory: a zig-zag delay line down to the bus
        pts = [f"400,{top + 76}"]
        for k in range(8):
            pts.append(f"{400 + (9 if k % 2 == 0 else -9)},{top + 104 + k * 4}")
        pts.append(f"400,{top + 140}")
        self.path("M" + " L".join(pts), sw=1.6, col=OXBLOOD)

    def render(self) -> str:
        s = self.s
        self.air()
        if s["kind"] == "mc":
            self.multicycle()
        elif s["kind"] == "pipe":
            self.pipeline()
        else:
            self.ooo()
        self.marks()
        seed = abs(hash_str(s["version"])) % 90 + 1
        title = f"No. {WORK_NO[s['version']]}, {s['title']}, version {s['version']}"
        sig = f'<text x="64" y="{H - 24}" font-family="Cormorant Garamond, Georgia, serif" font-size="20" font-style="italic" fill="{INK}" fill-opacity="0.75">{e(s["version"])}</text>'
        sig2 = f'<text x="{W - 64}" y="{H - 24}" text-anchor="end" font-family="Cormorant Garamond, Georgia, serif" font-size="15" font-style="italic" fill="{INK}" fill-opacity="0.55">{e(s["title"])}</text>'
        defs = (f'<defs><filter id="ink" x="-2%" y="-2%" width="104%" height="104%"><feTurbulence type="fractalNoise" baseFrequency="0.018" numOctaves="2" seed="{seed}" result="n"/>'
                f'<feDisplacementMap in="SourceGraphic" in2="n" scale="2.6"/></filter>'
                f'<filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="{seed}"/>'
                f'<feColorMatrix values="0 0 0 0 0.35  0 0 0 0 0.27  0 0 0 0 0.16  0 0 0 0.22 -0.03"/></filter></defs>')
        body = "".join(self.back) + "".join(self.parts)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{e(title)}">'
                f'<title>{e(title)}</title>{defs}<rect width="{W}" height="{H}" fill="{PAPER}"/>'
                f'<g filter="url(#ink)">{body}</g><rect width="{W}" height="{H}" filter="url(#grain)"/>'
                f'<rect x="14" y="14" width="{W - 28}" height="{H - 28}" fill="none" stroke="{INK}" stroke-opacity="0.35" stroke-width="1"/>{sig}{sig2}</svg>\n')


def hash_str(s: str) -> int:
    h = 0
    for ch in s:
        h = (h * 131 + ord(ch)) % 1000003
    return h


WORK_NO = {w[0]: i + 1 for i, w in enumerate(WORKS)}


# ---------------------------------------------------------------------------
# Data assembly
# ---------------------------------------------------------------------------

def assemble() -> tuple[list[dict], list[dict], list[dict]]:
    current = (ROOT / "cpu" / "VERSION").read_text(encoding="utf-8").strip()
    hist = {h["version"]: h for h in read_history()}
    tags = git_tags()
    runs = read_runs()
    specs = build_specs()
    missing = [s["version"] for s in specs if s["version"] not in hist]
    if missing:
        sys.exit(f"history rows missing for {missing}")
    known = {s["version"] for s in specs}
    extra = [v for v in hist if v not in known]
    if extra:
        print("note: history has versions with no artwork spec yet:", ", ".join(extra), file=sys.stderr)
    versions = []
    for i, s in enumerate(specs):
        v = s["version"]
        h = hist[v]
        ref = [r for r in runs if r["version"] == v and not r["fast"]]
        fast = [r for r in runs if r["version"] == v and r["fast"]]
        best = max(ref, key=lambda r: r["dmips_mhz"]) if ref else None
        bestf = max(fast, key=lambda r: r["dmips_mhz"]) if fast else None
        if v == current and v not in tags:
            status = "in progress"
        elif v in tags or not tags:
            status = "tagged"
        else:
            status = "untagged"
        versions.append({
            "no": i + 1, "version": v, "title": s["title"], "caption": s["caption"],
            "date": h["date"], "date_fr": fr_date(h["date"]) if h["date"] else "",
            "kind": s["kind"], "status": status, "tag": f"cpu-v{v}",
            "register": h["summary"], "register_html": h["summary_html"], "breaking": h["breaking"],
            "units": unit_lines(s), "marks": s["marks"], "width": s["retire"], "alus": s["alus"],
            "dmips_ref": best["dmips_mhz"] if best else None,
            "clocks_ref": best["clocks"] if best else None,
            "dmips_fast": bestf["dmips_mhz"] if bestf else None,
            "ref_run": best["time"] if best else None,
            "art": f"art/v{v}.svg",
        })
    return versions, specs, runs


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&amp;family=Jost:wght@300;400;500&amp;display=swap">')


SITE_URL = "https://monstercameron.github.io/RISC-V-FPGA-CPU-Research/"
# Social preview image: an existing artwork under docs/ (SVG, as published).
SITE_IMAGE = SITE_URL + "art/v0.11.2.svg"


def page(title: str, desc: str, body: str, active: str, path: str, extra_head: str = "", body_class: str = "") -> str:
    def nav(href, label, key):
        cur = ' aria-current="page"' if key == active else ""
        return f'<a href="{href}"{cur}>{label}</a>'
    canon = SITE_URL + ("" if path == "index.html" else path)
    return f"""<!doctype html>
<html lang="en" class="no-js">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canon)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{e(canon)}">
<meta property="og:image" content="{e(SITE_IMAGE)}">
<meta property="og:site_name" content="Atelier">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{e(SITE_IMAGE)}">
<meta name="color-scheme" content="light dark">
{FONTS}
<link rel="stylesheet" href="assets/style.css">
{extra_head}
<link rel="stylesheet" href="assets/polish.css">
<script>document.documentElement.className = 'js';</script>
</head>
<body class="{body_class}">
<a class="skip" href="#main">Skip to content</a>
<header class="masthead">
  <a class="brand" href="index.html"><span class="brand-mark" aria-hidden="true"></span><span>Atelier</span></a>
  <nav aria-label="Main">{nav("index.html", "Accueil", "home")}{nav("gallery.html", "La Galerie", "gallery")}{nav("journal.html", "Le Journal", "journal")}<a href="{REPO_URL}" rel="noopener">Source</a></nav>
</header>
<main id="main">
{body}
</main>
<footer class="colophon">
  <p class="ornament" aria-hidden="true">· · ·</p>
  <p>Art and science over time. Every figure for this processor comes from simulation of the design in
  <a href="{REPO_URL}" rel="noopener">the repository</a>; nothing here is a hardware measurement of it.
  The one native figure, a laptop's Cortex-X925 running the scaled 7-Zip kernel, is a point of comparison and is labelled as such.
  The drawings are generated from the architecture history, not photographs of silicon.</p>
  <p class="small">Source code and full record: <a href="{REPO_URL}" rel="noopener">{REPO_URL.replace("https://", "")}</a>.</p>
  <p class="small">Generated by <code>scripts/build_site.py</code>. Fonts from Google Fonts; no scripts from elsewhere, no trackers.</p>
</footer>
<script src="assets/site.js" defer></script>
<script src="assets/polish.js" defer></script>
</body>
</html>
"""


def fmt_dm(x) -> str:
    return f"{x:.2f}" if x is not None else ""


# Dhrystone figures for versions with no logged run, from DEVLOG.md rows.
UNLOGGED_DHRYSTONE = {
    "0.14.6": "An unlogged fast-runtime run measured 27.89 DMIPS/MHz (simulated); "
              "the probe counts 15,658 / 10,202 region clocks.",
}

# Probe-only Dhrystone figures (region clocks, reference / fast runtime, simulated),
# from each version's history row; these versions have no logged run.
PROBE_DHRYSTONE = {
    "0.14.7": ("15,658 / 10,202", "unchanged"),
    "0.14.8": ("15,658 / 10,202", "unchanged"),
    "0.14.9": ("15,654 / 10,179", ""),
    "0.14.10": ("15,654 / 10,179", ""),
    "0.14.11": ("15,654 / 10,179", ""),
    "0.14.12": ("15,654 / 10,179", ""),
    "0.14.13": ("15,654 / 10,177", ""),
    "0.15.0": ("15,654 / 10,177", "defaults keep all timing"),
    "0.15.2": ("15,732 / 10,139", "reference 0.5% slower than 0.15.1"),
    "0.15.3": ("15,732 / 10,139", "unchanged"),
    "0.15.4": ("15,732 / 10,139", "unchanged with the buffer off"),
    "0.15.5": ("15,732 / 10,139", "unchanged"),
    "0.15.6": ("15,698 / 10,127", ""),
    "0.15.7": ("15,703 / 10,127", ""),
    "0.16.0": ("15,703 / 10,127", "defaults keep timing exactly"),
    "0.16.1": ("15,703 / 10,127", ""),
    "0.16.2": ("15,706 / 10,127", "default N_MISS 1 neutral"),
    "0.17.0": ("15,706 / 10,127", "unchanged with the FPU built in"),
    "0.17.1": ("15,706 / 10,127", "unchanged with and without the FPU"),
    "0.17.2": ("15,706 / 10,127", "unchanged with and without the FPU"),
    "0.17.3": ("15,706 / 10,127", "bit-exact with 0.17.2"),
    "0.17.4": ("15,706 / 10,127", "unchanged"),
    "0.18.0": ("15,706 / 10,127", "unchanged with the vector option off"),
}

# The second measure: the LZMA benchmark kernel of 7-Zip, scaled down to fit the
# simulator. Compress / decompress MIPS/MHz, from the DEVLOG.md rows of
# 2026-11-21 (16:00 to 16:50, 16:55, 17:20, 18:05 to 18:10). Simulation of a scaled
# kernel, except the native row; none of these is a 7-Zip benchmark score.
# The 0.16.1 row is from its history row; the full-size (d22) goal from the DEVLOG.md
# row of 2026-11-21 20:34 (cpu/7zip-benchmark-targets.md), and the d22 goal run in the
# deciding configuration on 0.15.4 from the DEVLOG.md row of 2026-11-21 21:24 to 21:53,
# and on 0.16.0 with four misses in flight from the row of 2026-11-21 23:03 to 00:21.
SEVENZIP = [
    # (label, note, compress, decompress, style)
    ("Goal, scaled kernel", "about; derived from 10,000 MIPS in 7-Zip at 4 GHz", 10.9, 3.35, "goal"),
    ("Cortex-X925, native", "laptop core running the same scaled kernel natively; not a simulation", 8.34, 2.59, "native"),
    ("0.16.1 out of order, 64 KiB caches", "simulated, scaled kernel; 0.16.2 and 0.17.0 count within 0.02% of its clocks", 9.41, 3.29, "sim"),
    ("0.14.6 out of order, 64 KiB caches", "simulated, scaled kernel; where the council's 7-Zip phase began", 7.46, 2.89, "sim"),
    ("0.14.6 out of order, 4 KiB caches", "simulated, scaled kernel; the FPGA-class configuration", 3.39, 2.56, "sim"),
    ("Multicycle core", "simulated, scaled kernel; 0.14.6 tree", 1.61, 1.69, "sim"),
    ("Pipelined core", "simulated, scaled kernel; 0.14.6 tree", 0.96, 0.89, "sim"),
    ("Goal, full-size (d22) kernel", "about; the same 10,000 MIPS goal, calibrated on the full-size kernel, a different and larger workload", 2.03, 2.18, "goal"),
    ("0.15.4 out of order, full-size (d22) kernel, deciding configuration",
     "simulated, sampled (30 pieces per phase, 95% CI ±10.9% / ±22.9%); loads at four clocks, a 16-beat recent-beat buffer, 4 MiB L2 at 20 clocks, "
     "memory 350 clocks away, one miss at a time; goal not met, 75% / 91%", 1.53, 1.98, "sim"),
    ("0.16.0 out of order, full-size (d22) kernel, deciding configuration, four misses in flight",
     "simulated, sampled (60 pieces per phase, 95% CI ±6.8% / ±10.2%, low ends 2.04 / 2.09); as above but N_MISS 4 and MEM_GAP 8; "
     "goal met in point estimate, 108% / 107%; the decompress interval reaches below the goal", 2.19, 2.32, "sim"),
]

# Per version: (compress, decompress MIPS/MHz at 64 KiB caches, or None, and the rest
# of the line), all from that version's history row. Simulation of the scaled kernel.
SEVENZIP_BY_VERSION = {
    "0.14.6": (7.46, 2.89, "at 64 KiB caches (3.39 / 2.56 at 4 KiB)"),
    "0.14.7": (7.65, 3.23, "at 64 KiB caches (1,060,024 / 157,281 clocks at 4 KiB)"),
    "0.14.8": (None, None, "473,020 / 135,703 clocks compress / decompress at 64 KiB caches"),
    "0.14.9": (7.72, None, "MIPS/MHz compress at 64 KiB caches; decompress unchanged at 135,703 clocks"),
    "0.14.10": (None, None, "468,772 / 135,703 clocks at 64 KiB caches with the default one-clock load; about 630,600 / 178,600 at four"),
    "0.14.11": (None, None, "468,772 / 135,703 clocks at 64 KiB caches, unchanged"),
    "0.14.12": (None, None, "468,772 / 135,703 clocks at 64 KiB caches, unchanged"),
    "0.14.13": (7.76, 3.25, "at 64 KiB caches (1,055,247 / 156,197 clocks at 4 KiB)"),
    "0.15.0": (None, None, "466,256 / 134,773 clocks at 64 KiB caches with the default SoC; 6.43 / 2.67 MIPS/MHz with a 1 MiB L2 and MEM_LAT 100"),
    "0.15.1": (7.97, 3.26, "at 64 KiB caches (1,051,391 / 156,124 clocks at 4 KiB)"),
    "0.15.2": (9.16, 3.26, "at 64 KiB caches (983,418 / 155,941 clocks at 4 KiB)"),
    "0.15.3": (None, None, "395,001 / 134,501 clocks at 64 KiB caches, unchanged"),
    "0.15.4": (None, None, "395,001 / 134,501 clocks at 64 KiB caches with the buffer off, unchanged; "
                           "with loads at four clocks on 0.15.1, a 16-beat buffer saves 6.5% / 8.5% of clocks, 32 beats 8.3% / 9.3%"),
    "0.15.5": (None, None, "395,001 / 134,501 clocks at 64 KiB caches, unchanged"),
    "0.15.6": (9.20, 3.28, "at 64 KiB caches (393,569 / 133,854 clocks)"),
    "0.15.7": (9.37, 3.27, "at 64 KiB caches (974,370 / 154,514 clocks at 4 KiB)"),
    "0.16.0": (None, None, "386,369 / 133,976 clocks at 64 KiB caches with the default single miss, exactly as 0.15.7; "
                           "with a 1 MiB L2 at 12 clocks, MEM_LAT 100 and N_MISS 4, compression 7.56 to 8.30 MIPS/MHz (-9.0% clocks) "
                           "and decompression -2.4% clocks, under the stated optimistic assumptions"),
    "0.16.1": (9.41, 3.29, "at 64 KiB caches (973,966 / 152,756 clocks at 4 KiB)"),
    "0.16.2": (None, None, "384,788 / 133,243 clocks at 64 KiB caches with the default single miss; "
                           "with a 1 MiB L2 at 12 clocks, MEM_LAT 100 and N_MISS 4, -1.0% clocks at a 64 KiB data cache "
                           "and -4.3% / -0.5% compress / decompress at 4 KiB"),
    "0.17.0": (None, None, "384,788 / 133,243 clocks at 64 KiB caches, unchanged with the FPU built in; "
                           "604,503 / 229,974 at the deciding knobs, also unchanged"),
    "0.17.1": (None, None, "384,788 / 133,243 clocks at 64 KiB caches, unchanged with and without the FPU"),
    "0.17.2": (None, None, "384,788 / 133,243 clocks at 64 KiB caches, unchanged with and without the FPU"),
    "0.17.3": (None, None, "384,788 / 133,243 clocks at 64 KiB caches, unchanged with and without the FPU"),
    "0.17.4": (None, None, "384,788 / 133,243 clocks at 64 KiB caches, unchanged"),
    "0.18.0": (None, None, "384,788 / 133,243 clocks at 64 KiB caches and 974,219 / 153,238 at 4 KiB, equal to the baseline"),
}


def sevenzip_html(version: str) -> str:
    z = SEVENZIP_BY_VERSION.get(version)
    if not z:
        return ""
    c, d, rest = z
    if c is not None and d is not None:
        head = f"{c:.2f} / {d:.2f} MIPS/MHz compress / decompress {rest}"
    elif c is not None:
        head = f"{c:.2f} {rest}"
    else:
        head = rest
    return (f'<span class="aside z7">Scaled 7-Zip LZMA kernel: {e(head)}; simulated, not a 7-Zip score.</span>')


def perf_html(v: dict) -> str:
    z7 = sevenzip_html(v["version"])
    if v["dmips_ref"] is None:
        probe = PROBE_DHRYSTONE.get(v["version"])
        if probe:
            clocks, why = probe
            return (f'<p class="perf none">Dhrystone: no logged run for this version; probe numbers only: '
                    f'{e(clocks)} region clocks, reference / fast runtime, simulated{"; " + e(why) if why else ""}.{z7}</p>')
        note = UNLOGGED_DHRYSTONE.get(v["version"])
        if note:
            return f'<p class="perf none">Dhrystone: no logged run yet. {e(note)}{z7}</p>'
        return ('<p class="perf none">Dhrystone: no run logged for this version yet. '
                f'Simulated results are recorded in the journal as they are measured.{z7}</p>')
    extra = ""
    if v["dmips_fast"] is not None:
        extra = f' <span class="aside">(fast runtime: {v["dmips_fast"]:.2f})</span>'
    return (f'<p class="perf"><span class="num">{v["dmips_ref"]:.2f}</span> DMIPS/MHz'
            f'<span class="tag">simulated, reference runtime</span>{extra}{z7}</p>')


def sevenzip_plate() -> str:
    top = 12.0
    rows = []
    for label, note, c, d, style in SEVENZIP:
        bars = []
        for key, val, name in (("c", c, "compress"), ("d", d, "decompress")):
            bars.append(f'<div class="zb {key}"><span class="bar" style="--f:{val / top:.4f}" '
                        f'title="{e(label)}: {name} {val:.2f} MIPS/MHz"></span>'
                        f'<span class="val">{val:.2f}<span class="sr-only"> MIPS/MHz {name}</span></span></div>')
        rows.append(f'<li class="zrow {style}"><p class="zlab">{e(label)} <span class="znote">{e(note)}</span></p>{"".join(bars)}</li>')
    return f"""
<section class="plate" aria-labelledby="z7-h">
  <h2 id="z7-h">Le Second Étalon</h2>
  <p class="small">A second measure beside Dhrystone: the LZMA benchmark kernel of 7-Zip, scaled down to run in the simulator, in instructions per clock
  (MIPS per MHz) for compression and decompression. Every row is a simulation of that scaled kernel except the Cortex-X925 row, a native run of the same kernel on a laptop core.
  None of these is a 7-Zip benchmark score or a hardware result for this processor. The goal is about 10.9 / 3.35 on the scaled kernel, derived from a 10,000 MIPS single-thread 7-Zip rating at 4 GHz;
  the same goal on the full-size (d22) kernel is about 2.03 / 2.18. The last three rows are that full-size kernel, a different, larger workload whose bars do not compare with the rows above;
  in the deciding configuration (slow loads, a large and distant memory) version 0.15.4 with one miss at a time reaches 1.53 / 1.98 in simulation (75% / 91%), and version 0.16.0 with four misses in flight
  reaches 2.19 / 2.32 (108% / 107%): the goal is met in point estimate, though the decompress interval reaches below it.</p>
  <p class="legend small"><span class="sw z-c"></span>compress <span class="sw z-d"></span>decompress <span class="sw z-goal"></span>goal (outlined)</p>
  <ol class="zchart">{"".join(rows)}</ol>
  <p class="small">Scale: 0 to {top:g} MIPS/MHz, linear. Out-of-order rows under Verilator, whole program; multicycle and pipelined under Icarus.</p>
</section>"""


# A third measure: the QuickJS-ng 0.18.0 bytecode interpreter running nine kernels
# (cpu/js-benchmark-targets.md, commit 4c64892). Each figure is the geometric mean over the
# nine timed calls of (laptop cycles / our clocks): 1.0 is the laptop's own rate per clock.
# Baseline on architecture 0.17.0 from that file's tables; the 1 MiB instruction-cache probe
# from the DEVLOG.md row of 2026-11-22 02:12 to 02:16.
JSBENCH = [
    # (label, note, laptop-relative rate per clock, fraction of goal or None, style)
    ("Goal", "1.5x the laptop per clock, on every kernel and as the geometric mean", 1.5, None, "goal"),
    ("Cortex-X925, native", "the laptop core running the same engine, harness and script; median of 16 runs, CPU cycle counter; not a simulation", 1.0, None, "native"),
    ("0.17.0 out of order, hard float, 64 KiB caches", "simulated, flat memory, 16 sampled pieces per kernel; no kernel reaches the goal", 0.844, 56.3, "sim"),
    ("0.17.0 out of order, soft float, 64 KiB caches", "simulated, as above with the FPU off and compiler-rt, 8 pieces per kernel; faster than hard float through instruction-cache layout", 0.916, 61.1, "sim"),
    ("0.17.0 out of order, hard float, 1 MiB instruction cache", "a probe, not a design: simulated, one piece per kernel, 500K warm-up", 1.15, 76.0, "sim"),
    ("0.17.0 out of order, hard float, 7-Zip's deciding configuration", "simulated, slow loads and a large distant memory, 4 pieces per kernel with wide intervals; the order of magnitude is the result", 0.284, 18.9, "sim"),
]


def js_plate() -> str:
    top = 1.6
    rows = []
    for label, note, r, frac, style in JSBENCH:
        extra = f"; {frac:g}% of the goal" if frac is not None else ""
        fr = f"{r:.2f}" if r >= 1 else f"{r:.3f}"
        rows.append(f'<li class="zrow {style}"><p class="zlab">{e(label)} <span class="znote">{e(note + extra)}</span></p>'
                    f'<div class="zb c"><span class="bar" style="--f:{r / top:.4f}" title="{e(label)}: {fr}x the laptop per clock"></span>'
                    f'<span class="val">{fr}x<span class="sr-only"> the laptop per clock</span></span></div></li>')
    return f"""
<section class="plate" aria-labelledby="js-h">
  <h2 id="js-h">L'Interprète</h2>
  <p class="small">A third measure: JavaScript, run by the QuickJS-ng 0.18.0 bytecode interpreter (no JIT) through nine kernels: properties, a scheduler, a fluid stencil, SHA-256, JSON, regular expressions,
  strings, a DOM-like tree and closures. Each bar is the geometric mean over the nine of the laptop's clocks divided by ours for the same timed call, so 1.0 is the laptop's own rate per clock.
  The goal is 1.5x on every kernel and as the mean. The laptop row is a native measurement; every other row is a simulation of this processor, not a hardware result, and the flat-memory rows flatter it
  against the laptop's real caches and memory.</p>
  <ol class="zchart">{"".join(rows)}</ol>
  <p class="small">Scale: 0 to {top:g}x the laptop per clock, linear. Out-of-order rows under Verilator, sampled from rv_iss checkpoints with a 2M-instruction warm-up; output checked against the native run by hash.</p>
</section>"""


def medium(kind: str) -> str:
    return {"mc": "ink and ochre on vellum; simulated",
            "pipe": "ink, slate and ochre on vellum; simulated",
            "ooo": "ink, oxblood and gold leaf on vellum; simulated"}[kind]


def slug(v: str) -> str:
    return "v" + v.replace(".", "-")


def alt_text(v: dict, s: dict) -> str:
    kinds = {"mc": "a multicycle core", "pipe": "a pipelined core", "ooo": "an out-of-order core"}
    parts = [f"Abstract ink drawing of the processor at version {v['version']}, {kinds[v['kind']]}."]
    if s["kind"] == "ooo":
        parts.append(f"Blocks for a {s['rob']}-entry reorder buffer, {s['prf']} physical registers, a {s['iq']}-entry issue queue, "
                     f"{s['alus']} integer units, and instruction and data caches above a bus.")
        if s["tage"]:
            parts.append(f"{'Six' if s['tg_n'] == 6 else 'Four'} coloured arcs around the predictor rings stand for the tagged global-history tables, longer arcs for longer histories.")
        if s["l2"]:
            parts.append("A dashed second-level cache sits between the two caches, with a zig-zag delay line down to the bus for the distant memory.")
        if s["l0"]:
            parts.append("A dashed row of sixteen small cells under the load ports is the recent-beat buffer, off by default.")
        if s["ldwait"]:
            parts.append("A small grid of bits with a clock hand beside it is the load-wait table that is cleared at intervals.")
        if s["n_miss"]:
            parts.append("Eight small slots above the data cache, one solid and seven dashed, are the reads that may be in flight, and a dashed line climbing from the bus is the split answer channel.")
        if s["fuse_x"]:
            parts.append("A gold register under the last rename slot hooks back to the first slot: fusion carried into the next rename clock.")
        if s["wake_fill"]:
            parts.append("A gold dotted line runs back along the waiting read slots and touches each one: loads woken when their answer arrives.")
        if s["fpu"]:
            parts.append("Four small dashed sage discs below the execution row are the floating-point ports, two with oxblood centres for the multiply-add units and one notched for the pipelined divider; "
                         "a gold row in the register file stands for the f registers, and a gold flag on the retire column for the exception flags settled at retirement.")
        if s["fp_lat"]:
            parts.append("Two gold beats under the first multiply-add port and three under the second: an add in two clocks, a multiply in three.")
        if s["fp_div"]:
            parts.append("A gold radical sign inside the notched divider port: divide and square root at shorter latencies.")
    elif s["kind"] == "pipe":
        parts.append(f"{len(s['stages'])} pipeline stages as coloured slabs, a branch target buffer drawn as rings, and two caches above a bus.")
    else:
        parts.append(f"A ring of {len(s['states'])} control states around the register file, {s['issue']} execution slot"
                     f"{'s' if s['issue'] > 1 else ''}, and the bus below.")
    return " ".join(parts)


def gallery_page(versions, specs) -> str:
    byv = {v["version"]: (v, s) for v, s in zip(versions, specs)}
    rooms = []
    for roman, label, name, blurb, a, b in ERAS:
        vs = [v for v in versions if a <= v["version"] or True]
        ia = next(i for i, v in enumerate(versions) if v["version"] == a)
        ib = next(i for i, v in enumerate(versions) if v["version"] == b)
        works = []
        for v in versions[ia:ib + 1]:
            s = byv[v["version"]][1]
            cur = ' <span class="badge">newest, in progress</span>' if v["status"] == "in progress" else ""
            marks = "".join(f"<li>{e(m)}</li>" for m in v["marks"][-3:])
            units = "".join(f"<tr><th scope='row'>{e(k)}</th><td>{e(val)}</td></tr>" for k, val in v["units"])
            brk = v["breaking"]
            works.append(f"""
<figure class="work" id="{slug(v['version'])}" data-index="{v['no'] - 1}" data-kind="{v['kind']}">
  <button class="frame" type="button" aria-label="View No. {v['no']}, {e(v['title'])}, version {v['version']}, enlarged">
    <span class="mat"><img src="{v['art']}" width="800" height="1000" loading="lazy" alt="{e(alt_text(v, s))}"></span>
  </button>
  <figcaption class="placard">
    <span class="no">No. {v['no']}</span>
    <h3>{e(v['title'])}</h3>
    <p class="ver">Version {v['version']}<span class="sep"> · </span>{e(v['date_fr'])}{cur}</p>
    <p class="medium">{medium(v['kind'])}</p>
    <p class="cap">{e(v['caption'])}</p>
    {perf_html(v)}
  </figcaption>
  <div class="detail" hidden>
    <h4>From the register</h4>
    <p>{v['register_html']}</p>
    <h4>The units</h4>
    <table class="units"><tbody>{units}</tbody></table>
    {('<h4>Marginalia</h4><ul class="marks">' + "".join(f"<li>{e(m)}</li>" for m in v["marks"]) + '</ul>') if v["marks"] else ''}
    <p class="small">Compatibility: {e(brk)}. <a href="{REPO_URL}/releases/tag/{v['tag']}" rel="noopener">Tag {e(v['tag'])}</a>{' (not yet tagged)' if v['status'] == 'in progress' else ''}.
    Areas and sizes are symbolic; counts follow the history row. Simulated, not a hardware measurement.</p>
  </div>
</figure>""")
        rooms.append(f"""
<section class="room" id="salle-{roman.lower()}" aria-labelledby="h-{roman.lower()}">
  <header class="room-head">
    <p class="room-no">{label}</p>
    <h2 id="h-{roman.lower()}">{e(name)}</h2>
    <p class="room-blurb">{e(blurb)}</p>
  </header>
  <div class="wall">
    <div class="rail" aria-hidden="true"></div>
    <div class="hang">{"".join(works)}</div>
    <div class="floor" aria-hidden="true"></div>
  </div>
</section>""")
    n = len(versions)
    intro = f"""
<section class="page-head">
  <p class="eyebrow">La Galerie</p>
  <h1>{n} portraits of a processor</h1>
  <p class="lede">Each drawing is generated from the architecture history: one canvas per version, its units sized and arranged by their recorded counts.
  Walk the rooms in order and the machine learns to fetch, to pair, to pipeline, to run out of order. Select a work to see it enlarged.</p>
  <p class="legend small"><span class="sw" style="--c:#c58f2c"></span>fetch, loads
     <span class="sw" style="--c:#7a2430"></span>rename, reorder buffer, stores
     <span class="sw" style="--c:#3f5a73"></span>execution, caches
     <span class="sw" style="--c:#7f9168"></span>registers, multiply
     <span class="sw" style="--c:#b8923a"></span>retirement, prediction</p>
</section>
<nav class="rooms-nav" aria-label="Rooms">{"".join(f'<a href="#salle-{r[0].lower()}"><span>{r[1]}</span> {e(r[2])}</a>' for r in ERAS)}</nav>
"""
    dialog = """
<dialog id="lightbox" aria-labelledby="lb-title">
  <div class="lb-inner">
    <button class="lb-close" type="button" aria-label="Close">&times;</button>
    <div class="lb-art"><img id="lb-img" alt=""></div>
    <div class="lb-text">
      <p class="no" id="lb-no"></p>
      <h2 id="lb-title"></h2>
      <p class="ver" id="lb-ver"></p>
      <p class="medium" id="lb-medium"></p>
      <p class="cap" id="lb-cap"></p>
      <div id="lb-perf"></div>
      <div id="lb-detail"></div>
      <div class="lb-nav"><button type="button" id="lb-prev">&larr; Previous</button><button type="button" id="lb-next">Next &rarr;</button></div>
    </div>
  </div>
</dialog>"""
    return page("La Galerie · Atelier RV64", "A gallery of generated drawings, one for each version of the RV64 simulated research CPU architecture. Drawings only; no hardware measurements.",
                intro + "".join(rooms) + dialog, "gallery", "gallery.html", body_class="gallery")


def chart_svg(versions) -> str:
    Wc, Hc = 1000, 460
    l, r, t, b = 70, 30, 40, 70
    pts = [v for v in versions if v["dmips_ref"] is not None]
    n = len(versions)
    xs = {v["version"]: l + (Wc - l - r) * (i + 0.5) / n for i, v in enumerate(versions)}
    top = max([v["dmips_ref"] for v in pts] + [v["dmips_fast"] or 0 for v in versions])
    ymax = 32 if top > 15 else (16 if top > 7.5 else 8)
    lo, hi = math.log2(0.2), math.log2(ymax)

    def Y(val):
        return t + (Hc - t - b) * (1 - (math.log2(val) - lo) / (hi - lo))
    out = [f'<svg class="chart" viewBox="0 0 {Wc} {Hc}" role="img" aria-labelledby="ch-t ch-d" xmlns="http://www.w3.org/2000/svg">',
           '<title id="ch-t">Dhrystone DMIPS per MHz by architecture version, simulated</title>',
           f'<desc id="ch-d">Best reference-runtime Dhrystone result in simulation for each version, on a logarithmic scale, rising from {pts[0]["dmips_ref"]:.2f} at version {pts[0]["version"]} to {pts[-1]["dmips_ref"]:.2f} at version {pts[-1]["version"]}. Simulation, not hardware.</desc>']
    # eras as washed bands
    bands = [("mc", "multicycle", OCHRE), ("pipe", "pipeline", SLATE), ("ooo", "out of order", OXBLOOD)]
    for kind, label, col in bands:
        idx = [i for i, v in enumerate(versions) if v["kind"] == kind]
        x0 = l + (Wc - l - r) * idx[0] / n
        x1 = l + (Wc - l - r) * (idx[-1] + 1) / n
        out.append(f'<rect x="{x0:.1f}" y="{t}" width="{x1 - x0:.1f}" height="{Hc - t - b}" fill="{col}" fill-opacity="0.09"/>')
        out.append(f'<text x="{(x0 + x1) / 2:.1f}" y="{t + 22}" text-anchor="middle" class="ct-era">{label}</text>')
    for val in [g for g in (0.25, 0.5, 1, 2, 4, 8, 16, 32) if g <= ymax]:
        y = Y(val)
        out.append(f'<line x1="{l}" y1="{y:.1f}" x2="{Wc - r}" y2="{y:.1f}" class="ct-grid"/>')
        out.append(f'<text x="{l - 10}" y="{y + 5:.1f}" text-anchor="end" class="ct-lab">{val:g}</text>')
    out.append(f'<text x="18" y="{(t + Hc - b) / 2:.0f}" transform="rotate(-90 18 {(t + Hc - b) / 2:.0f})" text-anchor="middle" class="ct-lab">DMIPS per MHz, simulated (log scale)</text>')
    for i, v in enumerate(versions):
        if (i % 2 == 0 and i < n - 2) or i == n - 1:  # every other label; the last never crowded
            x = xs[v["version"]]
            out.append(f'<text x="{x:.1f}" y="{Hc - b + 26}" text-anchor="end" transform="rotate(-50 {x:.1f} {Hc - b + 26})" class="ct-lab">{v["version"]}</text>')
    fast = [v for v in versions if v["dmips_fast"] is not None]
    if len(fast) > 1:
        d = " ".join(("M" if i == 0 else "L") + f"{xs[v['version']]:.1f} {Y(v['dmips_fast']):.1f}" for i, v in enumerate(fast))
        out.append(f'<path d="{d}" class="ct-fast"/>')
    d = " ".join(("M" if i == 0 else "L") + f"{xs[v['version']]:.1f} {Y(v['dmips_ref']):.1f}" for i, v in enumerate(pts))
    out.append(f'<path d="{d}" class="ct-line"/>')
    for v in pts:
        out.append(f'<a href="gallery.html#{slug(v["version"])}"><circle cx="{xs[v["version"]]:.1f}" cy="{Y(v["dmips_ref"]):.1f}" r="6.5" class="ct-dot"><title>No. {v["no"]}, {e(v["title"])} (version {v["version"]}): {v["dmips_ref"]:.2f} DMIPS/MHz, simulated</title></circle></a>')
    last = pts[-1]
    out.append(f'<text x="{xs[last["version"]] - 12:.1f}" y="{Y(last["dmips_ref"]) - 14:.1f}" text-anchor="end" class="ct-note">{last["dmips_ref"]:.2f}</text>')
    first = pts[0]
    out.append(f'<text x="{xs[first["version"]] + 12:.1f}" y="{Y(first["dmips_ref"]) + 26:.1f}" class="ct-note">{first["dmips_ref"]:.2f}</text>')
    out.append("</svg>")
    return "".join(out)


def journal_page(versions, days, runs) -> str:
    chart = chart_svg(versions)
    nruns = len(runs)
    body = [f"""
<section class="page-head">
  <p class="eyebrow">Le Journal</p>
  <h1>The notebook, day by day</h1>
  <p class="lede">The development log, set as an exhibition catalogue: findings, the timeline of each day, the commits, every Dhrystone run, a second measure from a scaled 7-Zip kernel and a third from a JavaScript interpreter. Text follows the
  <a href="{BLOB}DEVLOG.md" rel="noopener">DEVLOG.md</a> in the repository, which remains the full record. The small tag on each entry names where its time came from.</p>
</section>
<section class="plate" aria-labelledby="chart-h">
  <h2 id="chart-h">Instructions, per beat of the clock</h2>
  <p class="small">Best Dhrystone result per version with the reference runtime, in simulation (ink line, gold dots; each dot opens its portrait).
  The thin sage line is the fast runtime where it was run. {nruns} logged runs. No FPGA hardware was measured.</p>
  <div class="chart-wrap">{chart}</div>
</section>
{sevenzip_plate()}
{js_plate()}
<nav class="day-nav" aria-label="Days">{"".join(f'<a href="#d-{d["date"]}">{e(fr_date(d["date"]))}</a>' for d in days)}<a href="#runs">Les Essais</a></nav>
"""]
    for d in days:
        findings = "".join(f"<li>{md_inline(f)}</li>" for f in d["findings"])
        rows = []
        for r in d["timeline"]:
            full = r["text"]
            plain = md_plain(full)
            long = len(plain) > 260
            tagc = re.sub(r"[^a-z]", "", r["kind"].lower()) or "other"
            rows.append(f"""<li class="entry{' long' if long else ''}">
  <span class="when">{e(r['time'])}</span>
  <div class="what"><p class="txt">{md_inline(full)}</p>{'<button type="button" class="more" aria-expanded="false">Read on</button>' if long else ''}</div>
  {f'<span class="kind k-{tagc}" title="source of this timestamp">{e(r["kind"])}</span>' if r['kind'] else '<span class="kind none" aria-hidden="true"></span>'}
</li>""")
        commits = "".join(f"""<li><a class="hash" href="{REPO_URL}/commit/{c['hash']}" rel="noopener">{c['hash']}</a>
  <span class="when">{c['time'][:5]}</span> <span class="who">{e(c['author'])}</span>
  <span class="subj">{e(shorten(c['subject'], 140))}</span></li>""" for c in d["commits"])
        body.append(f"""
<section class="day" id="d-{d['date']}" aria-labelledby="h-{d['date']}">
  <header class="day-head">
    <p class="eyebrow">{e(d['date'])}</p>
    <h2 id="h-{d['date']}">{e(fr_date(d['date']))}</h2>
    <p class="day-title">{e(d['title'])}</p>
  </header>
  {('<h3 class="sub">Findings</h3><ol class="findings">' + findings + '</ol>') if findings else ''}
  {('<h3 class="sub">Timeline</h3><ol class="timeline">' + "".join(rows) + '</ol>') if rows else ''}
  {('<h3 class="sub">Commits</h3><ul class="commits">' + commits + '</ul>') if commits else ''}
</section>""")
    # run index
    vorder = {v["version"]: i for i, v in enumerate(versions)}
    run_rows = []
    for r in runs:
        run_rows.append(f"<tr><td>{e(r['time'][:16])}</td><td>{e(r['version'])}</td><td class='num'>{r['clocks']:,.1f}</td>"
                        f"<td class='num'>{r['dmips_mhz']:.4f}</td><td>{e(shorten(r['compiler'].replace('clang version 23.1.5 ', ''), 60))}</td></tr>")
    body.append(f"""
<section class="day runs" id="runs" aria-labelledby="h-runs">
  <header class="day-head"><p class="eyebrow">Index</p><h2 id="h-runs">Les Essais</h2>
  <p class="day-title">Every logged Dhrystone run, oldest first. Simulation results; compiler clang 23.1.5 at -O2. Per-run records are in the repository's <a href="{REPO_URL}/tree/main/devlog" rel="noopener">devlog folder</a>.</p></header>
  <div class="table-wrap"><table class="runs-table"><thead><tr><th>Run (US Eastern)</th><th>Version</th><th>Clocks / run</th><th>DMIPS/MHz</th><th>Build</th></tr></thead>
  <tbody>{"".join(run_rows)}</tbody></table></div>
</section>
<p class="more-link"><a href="{BLOB}DEVLOG.md" rel="noopener">Read the full DEVLOG.md on GitHub &rarr;</a></p>""")
    return page("Le Journal · Atelier RV64", "The development log of the RV64 research CPU project: dated entries, commits, simulated Dhrystone runs, a scaled 7-Zip kernel and a JavaScript interpreter. No hardware measurements of this processor.",
                "".join(body), "journal", "journal.html", body_class="journal")


def landing_page(versions) -> str:
    """Atelier brand landing page (site root). Every number comes from the history rows
    (cpu/architecture.md, via `versions`), the DEVLOG-derived run data in `versions`, or the
    ISA strings written in cpu/architecture.md section 1."""
    arch = (ROOT / "cpu" / "architecture.md").read_text(encoding="utf-8")
    isa_m = re.search(r"ISA string `(rv64im[^`]*)`", arch)
    isa_fd = re.search(r"ISA string with the option is `([^`]+)`", arch)
    isa = isa_m.group(1) if isa_m else "not found in cpu/architecture.md"
    newest = versions[-1]
    ref = max((v for v in versions if v["dmips_ref"]), key=lambda v: v["dmips_ref"])
    fast_all = [v for v in versions if v["dmips_fast"]]
    fast = max(fast_all, key=lambda v: v["dmips_fast"]) if fast_all else None
    n = len(versions)
    in_progress = newest["status"] == "in progress"
    fast_txt = (f'{fast["dmips_fast"]:.2f} with the labelled fast runtime (version {fast["version"]})'
                if fast else "no fast-runtime run logged")
    progress_txt = " (in progress, not yet tagged)" if in_progress else ""
    fd_txt = ""
    if isa_fd:
        fd_txt = f' (ISA string with F and D: <code>{e(isa_fd.group(1))}</code>)'
    arch_blob = BLOB + "cpu/architecture.md"
    devlog_blob = BLOB + "DEVLOG.md"
    body = f"""
<div class="atl">
<section class="atl-hero" aria-labelledby="atl-h">
  <p class="eyebrow">An original 64-bit RISC-V processor core</p>
  <h1 id="atl-h" class="atl-name">Atelier</h1>
  <p class="atl-slogan">Silicon, made in the open.</p>
  <p class="lede">Atelier is a fully libre 64-bit RISC-V processor core: out-of-order, written in SystemVerilog, and developed in simulation against a sequential golden model. It is designed to compete with the best Arm cores per clock, on the workloads people run.</p>
  <p><span class="atl-badge">Evidence: simulation only</span></p>
  <p class="cta"><a class="btn" href="#status">Current status</a><a class="btn ghost" href="{REPO_URL}" rel="noopener">Source</a></p>
</section>

<section class="atl-band" aria-labelledby="honest-h">
  <h2 id="honest-h" class="eyebrow">What this is, and what it is not</h2>
  <p class="atl-honest">Atelier is designed to compete with the best Arm cores. That is a design goal and a target we measure against, set per clock against an estimated Apple M6 reference. It is not a measured result.</p>
  <p>Today it exists only in simulation. There is no silicon and no board result yet, and no hardware performance is claimed. Every number on this site comes from simulation of the design and says so.</p>
</section>

<section aria-labelledby="for-h">
  <h2 id="for-h" class="eyebrow">Designed for</h2>
  <div class="atl-grid">
    <article class="atl-card">
      <p><span class="atl-tag goal">Goal</span> <span class="atl-tag sim">Simulation</span></p>
      <h3>JavaScript and the web</h3>
      <p>A JavaScript interpreter runs as a benchmark against a laptop reference. The result is tracked in the journal and is still below its goal in simulation.</p>
    </article>
    <article class="atl-card">
      <p><span class="atl-tag goal">Goal</span> <span class="atl-tag sim">Simulation</span></p>
      <h3>Compression</h3>
      <p>A scaled 7-Zip LZMA kernel. It was met in point estimate in simulation at version 0.16.0. That is not a hardware or frequency result.</p>
    </article>
    <article class="atl-card">
      <p><span class="atl-tag goal">Goal</span> <span class="atl-tag plan">Plan</span></p>
      <h3>Linux</h3>
      <p>A plan only. The current core has no MMU and cannot run Linux.</p>
    </article>
  </div>
</section>

<section aria-labelledby="goal-h">
  <h2 id="goal-h" class="eyebrow">Design goal</h2>
  <p>The per-clock goal is referenced to an Apple M6 estimate, bridged from laptop measurements. The reference is an estimate, not a measurement of an Apple M6, and the goal is a target, not a result.</p>
  <p class="small">Target documents: <a href="{BLOB}cpu/7zip-benchmark-targets.md" rel="noopener">cpu/7zip-benchmark-targets.md</a> and <a href="{BLOB}cpu/js-benchmark-targets.md" rel="noopener">cpu/js-benchmark-targets.md</a>.</p>
</section>

<section id="status" aria-labelledby="status-h">
  <h2 id="status-h" class="eyebrow">Current status</h2>
  <div class="atl-stats">
    <div class="atl-stat"><span class="atl-num">{e(newest['version'])}</span><span class="atl-lbl">Architecture version{progress_txt}, {e(newest['date_fr'])}. <span class="atl-tag sim">Simulation</span></span></div>
    <div class="atl-stat"><span class="atl-num atl-mono">{e(isa)}</span><span class="atl-lbl">Implemented ISA string. Not implemented: the A and C extensions and an MMU (cpu/architecture.md section 1).</span></div>
    <div class="atl-stat"><span class="atl-num">{ref['dmips_ref']:.2f}</span><span class="atl-lbl">Dhrystone DMIPS/MHz on the reference runtime (version {e(ref['version'])}). <span class="atl-tag sim">Simulation</span> A secondary benchmark; {e(fast_txt)}.</span></div>
    <div class="atl-stat"><span class="atl-num">{n}</span><span class="atl-lbl">Architecture versions in the gallery, each with its own drawing and a dated entry in the journal.</span></div>
  </div>
  <p class="small">The RV64F and D options and a vector subset exist as options of the out-of-order core, off by default{fd_txt}.</p>
  <p class="cta"><a class="btn ghost" href="journal.html">Read the journal</a><a class="btn ghost" href="{devlog_blob}" rel="noopener">DEVLOG</a><a class="btn ghost" href="{arch_blob}" rel="noopener">Architecture</a></p>
</section>

<section aria-labelledby="gallery-h">
  <h2 id="gallery-h" class="eyebrow">The gallery and the journal</h2>
  <div class="atl-grid">
    <article class="atl-card"><h3><a href="gallery.html">La Galerie</a></h3><p>One generated drawing for every architecture version, with a placard for each.</p></article>
    <article class="atl-card"><h3><a href="journal.html">Le Journal</a></h3><p>The development log as a dated timeline, with commits, findings and the index of runs.</p></article>
  </div>
</section>

<section aria-labelledby="libre-h">
  <h2 id="libre-h" class="eyebrow">Libre principles</h2>
  <ul class="atl-list">
    <li>RTL, tests, scripts and their licences are in the repository. Original work is MIT licensed (<a href="{BLOB}LICENSE" rel="noopener">LICENSE</a>).</li>
    <li>Third-party licences and notices are kept apart, in <a href="{BLOB}licenses/README.md" rel="noopener">licenses/</a>.</li>
    <li>Firmware is planned, not yet built. A hardware-specific licence has not been chosen.</li>
    <li>Each result cites the run that produced it in the journal, so it can be reproduced.</li>
  </ul>
</section>

<section aria-labelledby="build-h">
  <h2 id="build-h" class="eyebrow">Build and test</h2>
  <p>Nothing is downloaded and no FPGA is needed. From the repository root:</p>
  <pre class="atl-code"><code>python -B sim/cpu/suite.py --list
python -B sim/cpu/suite.py unit --jobs 1
python -B sim/cpu/suite.py release-patch --dry-run
python -B scripts/check_repo.py</code></pre>
</section>

<section aria-labelledby="road-h">
  <h2 id="road-h" class="eyebrow">Roadmap</h2>
  <p>Each stage has exit evidence, listed in cpu/architecture.md section 6. No dates are given.</p>
  <ul class="atl-list">
    <li><span class="atl-tag plan">Plan</span> C1: a real execution environment (traps, interrupts, counters, user mode).</li>
    <li><span class="atl-tag plan">Plan</span> C2 to C4: scalar breadth, memory correctness, scalar floating point.</li>
    <li><span class="atl-tag plan">Plan</span> C5 to C6: a complete vector engine and profile closure.</li>
    <li><span class="atl-tag plan">Plan</span> C7: an FPGA proof on an exact part. No board run is claimed yet.</li>
  </ul>
  <p class="small">Target: RVA23U64, in stages. Not compliant today (cpu/architecture.md section 5).</p>
</section>

<section aria-labelledby="links-h" class="atl-links">
  <h2 id="links-h" class="eyebrow">Links</h2>
  <p><a href="gallery.html">The gallery</a> &middot; <a href="journal.html">The journal</a> &middot; <a href="{devlog_blob}" rel="noopener">DEVLOG</a> &middot; <a href="{REPO_URL}" rel="noopener">The repository</a></p>
</section>
</div>
"""
    return page("Atelier · An open RISC-V processor core",
                "Atelier is an original, fully libre 64-bit RISC-V processor core, designed in simulation to compete with the best Arm cores. Simulation only: no silicon and no hardware result yet.",
                body, "home", "index.html",
                extra_head='<link rel="stylesheet" href="assets/landing.css">', body_class="home")


# ---------------------------------------------------------------------------

def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main():
    versions, specs, runs = assemble()
    days = read_journal()
    for v, s in zip(versions, specs):
        write(SITE / v["art"], Art(s).render())
    pub_versions = [{k: v[k] for k in v if k != "register_html"} for v in versions]
    write(SITE / "data" / "versions.json", json.dumps(pub_versions, indent=1, ensure_ascii=False) + "\n")
    write(SITE / "data" / "journal.json",
          json.dumps({"source": "DEVLOG.md", "days": days, "runs": runs}, indent=1, ensure_ascii=False) + "\n")
    write(SITE / "index.html", landing_page(versions))
    write(SITE / "gallery.html", gallery_page(versions, specs))
    write(SITE / "journal.html", journal_page(versions, days, runs))
    print(f"site: {len(versions)} artworks, {len(days)} days, "
          f"{sum(len(d['timeline']) for d in days)} timeline rows, {len(runs)} runs")


if __name__ == "__main__":
    main()
