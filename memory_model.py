"""Analytical Qwen3.8-27B memory plan. Python stdlib only; no RTL/board benchmark.
Run: python memory_model.py --out memory-model-results.json
GB is decimal; GiB/MiB/KiB are binary. Quantized profiles are capacity hypotheses.
"""
import argparse
import heapq
import json
import math
from pathlib import Path

H, I, V = 5120, 17408, 248320
L, A, R, Q, K, D = 64, 16, 48, 24, 4, 256
KH, VH, DK, DV = 16, 48, 128, 128
GiB, MiB, KiB = 2**30, 2**20, 2**10
TEXT_ELEMENTS = 26895998464
VISION_BYTES = 921460192
MATRICES = [(V, H, 1, "embedding"), (V, H, 1, "head"),
            (I, H, L, "gate"), (I, H, L, "up"), (H, I, L, "down"),
            (2*Q*D, H, A, "qgate"), (K*D, H, A, "k"),
            (K*D, H, A, "v"), (H, Q*D, A, "att_out"),
            (2*KH*DK+VH*DV, H, R, "dqkv"), (VH*DV, H, R, "dz"),
            (VH, H, R, "da"), (VH, H, R, "db"), (H, VH*DV, R, "dout")]
SMALL_ELEMENTS = TEXT_ELEMENTS - sum(n*k*c for n,k,c,_ in MATRICES)
STATE = R*VH*DK*DV*4
CONV = R*(2*KH*DK+VH*DV)*4*2
KV_PER_TOKEN = A*2*K*D*2
DENSE_MACS = sum(n*k*c for n,k,c,name in MATRICES if name != "embedding")

def matrix_bytes(n, k, count, bits):
    # Symmetric group-128 scales, BF16 scale per row/group. No zero points.
    row = math.ceil(k*bits/8)
    if bits != 16:
        row += math.ceil(k/128)*2
    return n*row*count

def weights(bits):
    resident = SMALL_ELEMENTS*2
    decode = SMALL_ELEMENTS*2
    for n,k,c,name in MATRICES:
        resident += matrix_bytes(n,k,c,bits)
        decode += matrix_bytes(1 if name == "embedding" else n,k,c,bits)
    return dict(bits=bits, text_resident_bytes=resident,
                active_text_vision_resident_bytes=resident+VISION_BYTES,
                decode_weight_read_bytes=decode)

def decode(bits, context, att="grouped_three_pass"):
    factor = {"ungrouped_three_pass":12, "grouped_three_pass":2,
              "grouped_online":1}[att]
    parts = dict(weights=weights(bits)["decode_weight_read_bytes"],
                 delta_state_read_write=2*STATE, conv_ring_read_write=2*CONV,
                 kv_scan=factor*KV_PER_TOKEN*context, kv_append=KV_PER_TOKEN,
                 logits_write=V*4)
    return dict(bits=bits, context=context, attention=att, parts=parts,
                modeled_bytes=sum(parts.values()),
                excluded="activation spills, DMA padding/metadata, refresh/turnaround, retries, cold load")

def burst_stream(burst, outstanding, latency_ns, gbps, count=4096):
    """Ideal shared response bus; slot frees at last beat; unlimited request issue.
    Fixed first-byte latency, no banks, no refresh, no compute backpressure.
    Returns a finite-stream result including fill and drain. This is not DRAM simulation.
    """
    slots = [0.0]*outstanding
    heapq.heapify(slots)
    bus_free = 0.0
    for _ in range(count):
        issue = heapq.heappop(slots)
        finish = max(issue+latency_ns*1e-9, bus_free) + burst/(gbps*1e9)
        bus_free = finish
        heapq.heappush(slots, finish)
    serial = burst/(latency_ns*1e-9 + burst/(gbps*1e9))/1e9
    conservative_slots = math.ceil(1+gbps*1e9*latency_ns*1e-9/burst)
    return dict(burst_bytes=burst, outstanding=outstanding, latency_ns=latency_ns,
                bus_gbps=gbps, stream_gbps=count*burst/bus_free/1e9,
                serial_gbps=serial, slots_for_full_rate_ideal=conservative_slots,
                response_reservation_bytes=outstanding*burst)

def report():
    assert SMALL_ELEMENTS > 0
    assert 2*TEXT_ELEMENTS == 53791996928
    assert STATE == 150994944 and KV_PER_TOKEN == 65536
    assert weights(16)["decode_weight_read_bytes"] == 2*(TEXT_ELEMENTS-V*H+H)
    profiles = [weights(b) for b in (16,8,4)]
    scenarios = [decode(b,s,a) for b in (16,8,4) for s in (32,4096,32768,262144)
                 for a in ("grouped_three_pass", "grouped_online")]
    for row in scenarios:
        row["memory_only_seconds_at_effective_GBps"] = {
            str(bw):row["modeled_bytes"]/(bw*1e9) for bw in (2,8,16,32)}
    capacity = []
    for b in (16,8,4):
        for s in (4096,32768,262144):
            n = weights(b)["active_text_vision_resident_bytes"]+STATE+CONV+KV_PER_TOKEN*s
            capacity.append(dict(bits=b,context=s,minimum_known_bytes=n,
                                 excluded="working scratch, padding, allocator/driver reserve, extra sequences"))
    latency = [burst_stream(b,q,ns,8) for ns in (100,500,2000)
               for b in (64,512,4096) for q in (1,2,4,8,16)]
    assert all(x["stream_gbps"] <= x["bus_gbps"]+1e-12 for x in latency)
    # Increasing queue depth cannot slow this ideal model.
    for ns in (100,500,2000):
        vals=[burst_stream(4096,q,ns,8)["stream_gbps"] for q in (1,2,4,8,16)]
        assert vals == sorted(vals)
    return dict(status="analytical planning; no actual checkpoint execution or measured hardware rate",
                assumptions=dict(group_size=128,scale_bytes=2,quantized="all text 2D matrices including embedding/head",
                    retained_bf16="text 1D/conv weights and all vision weights",state_dtype="FP32",kv_dtype="BF16",
                    dataflow="one sequence, one token; each weight read once; grouped six-head attention"),
                config_sha256="191e0af232104ed8b65258cf3fb2b842e288008baca7633c11b82a1ac7203aab",
                constants=dict(small_text_elements=SMALL_ELEMENTS,dense_macs_per_token=DENSE_MACS,
                    delta_state_bytes=STATE,conv_ring_bytes=CONV,kv_bytes_per_context_token=KV_PER_TOKEN),
                weights=profiles, decode=scenarios,capacity=capacity,latency=latency,
                dense_compute_seconds_at_200MHz={str(lanes):DENSE_MACS/(lanes*200e6) for lanes in (1,8,64,256)},
                prefill_weight_bytes_per_token_ideal={str(u):(weights(16)["decode_weight_read_bytes"]-2*H)/u+2*H
                    for u in (1,8,16,32)},
                notes=["Prefill number assumes each weight tile shared by U rows, including requested logits; ignores other traffic.",
                       "Last-position-only LM head has a different prefill count.",
                       "Online attention changes finite-precision/cast behavior; quality qualification required.",
                       "Eight-lane uncached GEMV input rereads add roughly dense BF16 weight bytes / 8."])

if __name__ == "__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",default="memory-model-results.json")
    args=ap.parse_args()
    data=report()
    Path(args.out).write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:data[k] for k in ("constants","weights","dense_compute_seconds_at_200MHz")},indent=2))
