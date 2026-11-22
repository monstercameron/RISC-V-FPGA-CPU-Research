"""Reproducible planning checks; no RTL, numerical-model or FPGA validation.

Run beside memory_model.py and reference-sources/:
  python plan_audit_checks.py --out plan-audit-checks.json
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import memory_model as memory

MODEL_REV = "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0"
TRANSFORMERS_REV = "1a55addd658aaa95b52871f5b72e91a6b91449b6"
SOURCE_LOCK_SHA256 = "627b2548f9c1c2a839aec66671331b75c7cf2c360681f602824f100260e418eb"
EXPECTED = {
    "config.json": "191e0af232104ed8b65258cf3fb2b842e288008baca7633c11b82a1ac7203aab",
    "model.safetensors.index.json": "77042094076611b69791a610065f28b7013b8c621795fa86ddccc8bac7d1b9df",
    "modeling_qwen3_5.py": "af05d0acfe79fff8aea1c75f93516a6a72bc80f6f901329a73e66a3866fe1e7c",
}
MiB = 2**20


def verify_sources(source_dir, lock_path):
    if hashlib.sha256(lock_path.read_bytes()).hexdigest() != SOURCE_LOCK_SHA256:
        raise ValueError('Source lock changed; version and review the lock before adopting new sources')
    lock = json.loads(lock_path.read_bytes())
    if lock.get('schema_version') != 1 or lock.get('model_revision') != MODEL_REV or lock.get('transformers_revision') != TRANSFORMERS_REV:
        raise ValueError('Unexpected source-lock schema or revisions')
    required = set(lock['files'])
    allowed = required | set(lock['mutable_documentation'])
    present = {p.name for p in source_dir.iterdir()}
    if required - present or present - allowed:
        raise ValueError(f'Source inventory mismatch: missing={sorted(required-present)}, unexpected={sorted(present-allowed)}')
    for name, item in lock['files'].items():
        path = source_dir / name
        if Path(name).name != name or path.is_symlink() or not path.is_file():
            raise ValueError(f'Invalid frozen source path: {name}')
        data = path.read_bytes()
        if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError(f'Frozen source changed: {name}')
        if not item.get('origin') or not item.get('revision'):
            raise ValueError(f'Missing provenance: {name}')
    return lock


def report(source_dir, lock_path=None):
    lock_path = lock_path or Path(__file__).parent / 'reference-source-lock.json'
    lock = verify_sources(source_dir, lock_path)
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(source_dir.iterdir()) if p.is_file()}
    for name, expected in EXPECTED.items():
        assert hashes[name] == expected, (name, "changed previously audited source")
    cfg = json.loads((source_dir / "config.json").read_bytes())
    generation = json.loads((source_dir / "generation_config.json").read_bytes())
    tokenizer = json.loads((source_dir / "tokenizer_config.json").read_bytes())
    image = json.loads((source_dir / "preprocessor_config.json").read_bytes())
    assert generation["eos_token_id"] == [248046, 248044]
    assert tokenizer["added_tokens_decoder"]["248046"]["content"] == "<|im_end|>"
    assert image["image_mean"] == image["image_std"] == [0.5] * 3
    assert cfg["text_config"]["hidden_size"] == memory.H

    # DDR-relative offsets; base address and usable extent come from the board adapter.
    reservations_mib = [("platform_reserve", 32), ("delta_state", 144),
                        ("conv_state_and_alignment", 4), ("kv_at_4096", 256),
                        ("external_workspace", 128), ("weight_stage_a", 128),
                        ("weight_stage_b", 128), ("constants_and_descriptors", 16)]
    allocations, cursor = [], 0
    for name, size in reservations_mib:
        allocations.append(dict(name=name, offset_bytes=cursor,
                                length_bytes=size * MiB, end_exclusive=cursor + size * MiB))
        cursor += size * MiB
    assert cursor == 836 * MiB
    assert all(a["end_exclusive"] == b["offset_bytes"]
               for a, b in zip(allocations, allocations[1:]))
    assert memory.STATE <= 144 * MiB and memory.CONV <= 4 * MiB
    assert memory.KV_PER_TOKEN * 4096 == 256 * MiB

    # Eight lanes, sixteen independent output rows per lane, reduction tile 32.
    # Embeddings remain row-major. Small vectors/conv weights are not packed as GEMV.
    lanes, contexts, ktile = 8, 16, 32
    packed = []
    for n, k, count, name in memory.MATRICES:
        if name == "embedding":
            continue
        npad = math.ceil(n / (lanes * contexts)) * lanes * contexts
        kpad = math.ceil(k / ktile) * ktile
        packed.append(dict(name=name, shape=[n, k], count=count,
                           padded_shape=[npad, kpad],
                           extra_bytes=(npad * kpad - n * k) * count * 2))
    extra = sum(x["extra_bytes"] for x in packed)
    assert extra == 75 * MiB
    tile_bytes = lanes * contexts * ktile * 2
    assert tile_bytes == 8192
    assert lanes * contexts * 4 <= 4 * 1024  # FP32 accumulators fit reserved allowance.
    assert 2 * tile_bytes <= 16 * 1024
    assert 4 * 4096 <= 16 * 1024  # Empty pool only; consumer-held tiles consume credits too.
    assert 4096 // 16 == 256     # 128-bit AXI data beats; still split at 4-KiB boundaries.

    scenarios = []
    logical = memory.decode(16, 4096)
    w = logical["parts"]["weights"] + extra
    other = logical["modeled_bytes"] - logical["parts"]["weights"]
    for mhz in (100, 200):
        dense = memory.DENSE_MACS / (lanes * mhz * 1e6)
        for ddr_gbps in (2, 4, 6, 8):
            host = w / 3e9  # Explicit hypothetical sustained service.
            ddr = (2 * w + other) / (ddr_gbps * 1e9)
            core_shared = (w + other) / (16 * mhz * 1e6)
            scenarios.append(dict(mhz=mhz, host_effective_GBps=3,
                                  ddr_effective_shared_GBps=ddr_gbps,
                                  dense_seconds=dense, host_seconds=host,
                                  ddr_staging_seconds=ddr,
                                  core_shared_128bit_port_seconds=core_shared,
                                  optimistic_overlap_floor_seconds=max(dense, host, ddr, core_shared),
                                  sum_of_modeled_service_times_seconds=dense + host + ddr + core_shared))
    logits = {str(t): t * memory.V * 4 for t in (1, 32, 512)}
    # Simulation wall time is distinct from cycles divided by the modeled device frequency.
    cycles = math.ceil(memory.DENSE_MACS / lanes)
    sim = {str(rate): cycles / rate for rate in (1e4, 1e5, 1e6)}
    return dict(status="planning arithmetic and source-identity checks only; all checks passed",
                model_revision=MODEL_REV, transformers_revision=TRANSFORMERS_REV,
                source_sha256=hashes, immutable_sources_verified=len(lock['files']),
                mutable_documentation_not_identity_checked=lock['mutable_documentation'],
                source_lock_sha256=hashlib.sha256(lock_path.read_bytes()).hexdigest(),
                generation=dict(eos_ids=generation["eos_token_id"],
                                default_is_sampling=generation["do_sample"],
                                proposed_bringup_mode="greedy, separate from model sampling defaults"),
                allocation=dict(regions=allocations, total_reserved_bytes=cursor,
                                free_bytes_at_1GiB=2**30-cursor, free_bytes_at_2GiB=2**31-cursor,
                                context_cap=4096, note="Illustrative reservation, requires validated physical DDR map"),
                layout=dict(lanes=lanes, accumulator_contexts=contexts, reduction_tile=ktile,
                            weight_tile_bytes=tile_bytes, accumulator_bytes=lanes*contexts*4,
                            packed_matrices=packed, extra_text_decode_bytes=extra,
                            packed_text_decode_weight_bytes=w,
                            note="Padding only; excludes per-tensor alignment, metadata, retries and spills"),
                logits_fp32_bytes=logits,
                performance_scenarios=scenarios,
                dense_only_simulator_wall_seconds_at_cycles_per_second=sim,
                open_evidence=["arithmetic accuracy and dtype traces", "FMA feedback latency and DSP mapping",
                               "complete RTL simulation", "DDR and PCIe DMA bandwidth",
                               "post-route timing/CDC", "checkpoint payload content and complete model logits"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-dir", type=Path, default=Path(__file__).parent / "reference-sources")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "plan-audit-checks.json")
    args = ap.parse_args()
    result = report(args.source_dir)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"],
                      "sources_hashed": len(result["source_sha256"]),
                      "reserved_MiB": result["allocation"]["total_reserved_bytes"] / MiB,
                      "padding_MiB": result["layout"]["extra_text_decode_bytes"] / MiB,
                      "example_200MHz_DDR4GBps": result["performance_scenarios"][5]}, indent=2))
