# Full forward-pass dimension ledger

Constructor-derived active tensor inventory, independently reconciled against all checkpoint shard keys/shapes by verify_checkpoint_shapes.py (see checkpoint-shape-audit.json). See plan.md for execution semantics.

| Learned tensor family | Shape (checkpoint output-first) | Multiplicity | Total elements |
|---|---|---:|---:|
| text.embedding | 248320 x 5120 | 1 | 1,271,398,400 |
| text.lm_head | 248320 x 5120 | 1 | 1,271,398,400 |
| text.final_norm.weight | 5120 | 1 | 5,120 |
| decoder.input_norm.weight | 5120 | 64 | 327,680 |
| decoder.post_mixer_norm.weight | 5120 | 64 | 327,680 |
| ffn.gate | 17408 x 5120 | 64 | 5,704,253,440 |
| ffn.up | 17408 x 5120 | 64 | 5,704,253,440 |
| ffn.down | 5120 x 17408 | 64 | 5,704,253,440 |
| full_attention.q_and_gate | 12288 x 5120 | 16 | 1,006,632,960 |
| full_attention.k | 1024 x 5120 | 16 | 83,886,080 |
| full_attention.v | 1024 x 5120 | 16 | 83,886,080 |
| full_attention.out | 5120 x 6144 | 16 | 503,316,480 |
| full_attention.q_norm | 256 | 16 | 4,096 |
| full_attention.k_norm | 256 | 16 | 4,096 |
| delta.qkv | 10240 x 5120 | 48 | 2,516,582,400 |
| delta.z | 6144 x 5120 | 48 | 1,509,949,440 |
| delta.a | 48 x 5120 | 48 | 11,796,480 |
| delta.b | 48 x 5120 | 48 | 11,796,480 |
| delta.out | 5120 x 6144 | 48 | 1,509,949,440 |
| delta.conv.weight | 10240 x 1 x 4 | 48 | 1,966,080 |
| delta.dt_bias | 48 | 48 | 2,304 |
| delta.A_log | 48 | 48 | 2,304 |
| delta.gated_norm.weight | 128 | 48 | 6,144 |
| vision.patch.weight | 1152 x 3 x 2 x 16 x 16 | 1 | 1,769,472 |
| vision.patch.bias | 1152 | 1 | 1,152 |
| vision.position_table | 2304 x 1152 | 1 | 2,654,208 |
| vision.block.norm1.weight | 1152 | 27 | 31,104 |
| vision.block.norm1.bias | 1152 | 27 | 31,104 |
| vision.block.norm2.weight | 1152 | 27 | 31,104 |
| vision.block.norm2.bias | 1152 | 27 | 31,104 |
| vision.block.qkv.weight | 3456 x 1152 | 27 | 107,495,424 |
| vision.block.qkv.bias | 3456 | 27 | 93,312 |
| vision.block.out.weight | 1152 x 1152 | 27 | 35,831,808 |
| vision.block.out.bias | 1152 | 27 | 31,104 |
| vision.block.fc1.weight | 4304 x 1152 | 27 | 133,871,616 |
| vision.block.fc1.bias | 4304 | 27 | 116,208 |
| vision.block.fc2.weight | 1152 x 4304 | 27 | 133,871,616 |
| vision.block.fc2.bias | 1152 | 27 | 31,104 |
| vision.merger.norm.weight | 1152 | 1 | 1,152 |
| vision.merger.norm.bias | 1152 | 1 | 1,152 |
| vision.merger.fc1.weight | 4608 x 4608 | 1 | 21,233,664 |
| vision.merger.fc1.bias | 4608 | 1 | 4,608 |
| vision.merger.fc2.weight | 5120 x 4608 | 1 | 23,592,960 |
| vision.merger.fc2.bias | 5120 | 1 | 5,120 |

Text parameters: 26,895,998,464
Vision parameters: 460,730,096
Active-graph total: 27,356,728,560

These totals include biases and normalization parameters and exclude auxiliary MTP. The separate checkpoint-shape-audit.json classifies all 15 auxiliary MTP tensors and reconciles total payload bytes. Actual tensor data loading and packed-layout verification remain implementation work.
