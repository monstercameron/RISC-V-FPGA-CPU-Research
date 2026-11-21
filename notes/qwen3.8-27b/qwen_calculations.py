"""Analytical Qwen3.8-27B text inference estimates; no weights required."""
H, I, V = 5120, 17408, 248320
ffn = 3 * H * I
delta_proj = H * (10240 + 6144 + 96 + 6144)
attn_proj = H * (12288 + 1024 + 1024 + 6144)
head = H * V
mac = 64 * ffn + 48 * delta_proj + 16 * attn_proj + head
print(f'Projection MAC/token: {mac:,}; GFLOP-equivalent: {2*mac/1e9:.6f}')
for s in (4096, 32768, 131072, 262144):
    kv = 16 * 2 * 4 * 256 * s * 2
    attn = 4 * 16 * 24 * 256 * s
    print(f'S={s}: KV={kv/2**30:.3f} GiB; attention={attn/1e9:.6f} GFLOP/token')
state = 48 * 48 * 128 * 128 * 4
print(f'FP32 recurrent state: {state/2**20:.2f} MiB')
for bits in (16, 8, 4):
    size = 27e9 * bits / 8
    print(f'{bits}-bit nominal weights: {size/1e9:.2f} GB / {size/2**30:.2f} GiB')
for bandwidth in (25, 50, 100):
    print(f'{bandwidth} GB/s / ideal 13.5 GB stream = {bandwidth/13.5:.3f} token/s upper bound')
T = 4096
print(f'4096-token prefill projections all logits: {2*mac*T/1e12:.3f} TFLOP-equivalent')
print(f'Only final logits saves: {2*head*(T-1)/1e12:.3f} TFLOP-equivalent')
print(f'Ideal causal prefill attention: {2*16*24*256*T*(T+1)/1e12:.3f} TFLOP')
assert mac == 25621954560
assert state == 150994944
