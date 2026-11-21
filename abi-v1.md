# Accelerator ABI 1: bounded commands and ownership

Normative companion to [implementation-contract.md](implementation-contract.md) and [adapter protocol 1](adapter-v1.md), which defines session initialization, initial upload/seal and the tagged weight byte-range service. All integers are little-endian. Structures have no implicit padding. Values not defined here are rejected, and all reserved fields must be zero. `abi_v1.py` is an executable planning codec, **not** an implemented driver or RTL parser. Generate the implementation's shared header from this schema and test it independently against the examples before DMA is enabled.

## 1. Operations and transport

Opcodes: 0 QUERY_CAPS, 1 REGISTER_MODEL, 2 REGISTER_CONTEXT, 3 RESET_CONTEXT, 4 EVALUATE, 5 CANCEL. Opcode 6 and on-device generation are **unsupported in ABI 1**. The host may sample returned logits and submit the next token; the core still executes the complete forward graph. No undocumented max-new-tokens/result union exists. A future generation ABI must version those fields. Sampling does not change the committed count until the selected token is consumed successfully.

One numerical command is active. A separately serviced control mailbox handles QUERY_CAPS and CANCEL while it runs. Model/context registration and reset require an idle, positively drained device. Before normal commands, the driver registers physical regions, uploads immutable tables, registers the model, then registers and initializes a context. There is no user-supplied physical-address escape hatch.

The simulation transport exposes the same register window. A board adapter maps the following **relative offsets**, in a kernel-owned BAR/CSR aperture of at least 4 KiB. The absolute BAR and generated board CSR mapping/hash are recorded in the adapter build manifest, never guessed from another board.

| Offset | Bytes | Direction / function |
|---|---:|---|
| 0x000 | 256 | Device capability record, read-only |
| 0x100 | 256 | Host command mailbox |
| 0x200 | 64 | Device terminal command completion |
| 0x300 | 256 | Host QUERY_CAPS/CANCEL mailbox |
| 0x400 | 64 | Device control acknowledgement |
| 0x500 | 64 | Trusted driver region-registration mailbox |
| 0x540 | 64 | Device region-registration acknowledgement |
| 0x600 | 4 | Doorbell: write exactly 1=command, 2=control, 4=region; adapter1 additionally defines8/16/32/64 |
| 0x604 | 4 | Status: bit0 command-ready,1 control-ready,2 region-ready,3 completion-valid,4 control-ack-valid,5 region-ack-valid,6 offline; adapter1 adds bits7..9 |
| 0x608 | 4 | Host acknowledgement W1C: bit3/4/5 releases corresponding result slot; adapter1 adds bit9 |

Driver serialization prevents torn writes: verify READY; fill mailbox; apply OS DMA/MMIO release ordering; ring once. The adapter atomically snapshots a complete mailbox and clears READY before processing. Results are fully visible before VALID; host uses acquire ordering before reading and W1C acknowledgement after copying. Do not overwrite a valid unacknowledged result. The result slot reserves space before issue, so host non-drain stalls new commands rather than discarding completions. IRQs are an optional notification; polling status is sufficient. Offline status prohibits new doorbells except a platform-specific reset/re-enumeration outside this ABI. The control path has its own storage and cannot be blocked by numerical command output credits.

QUERY_CAPS uses zero context/epoch/payload and returns a normal control acknowledgement; capabilities remain in the read-only record. Region registration is a trusted-driver operation while idle/drained; its acknowledgement uses the common completion shape with command ID=region handle, context/epoch=descriptor owner, status, opcode0x103, failing layer0xffffffff and zero other fields. Registration can add a new handle; a generation change replaces the same slot only after proven quiescence. Unregister uses kind=0 and length=0, all other fields zero except handle; it must match the existing generation and be unused by any registered model/context. Unregistering a referenced region fails BUSY. Release model/context by RESET_CONTEXT plus a fresh device session in ABI 1; dynamic model eviction is deferred.

## 2. Command: 256 bytes, 64-byte aligned

| Offset | Type | Meaning |
|---|---|---|
| 0 | u32 | Magic 0x314d4c4c (`LLM1`) |
| 4 / 6 | u16 / u16 | Major=1 / opcode |
| 8 / 12 | u32 / u32 | Flags / numerical profile: 0 REF32, 1 BF16-P0 |
| 16 / 24 / 32 | u64 each | Command ID / context ID / context epoch |
| 40 | u64 | Expected committed tokens; **CANCEL instead uses target command ID** |
| 48 / 56 | u64 each | Model-table handle / layout-table handle |
| 64 / 72 | u64 each | Input-table handle / state-table handle |
| 80 / 88 | u64 each | Output-table handle / workspace-table handle |
| 96 | u64 | First causal position; must equal committed tokens for EVALUATE |
| 104 / 108 / 112 / 116 | u32 each | New token count / context capacity / media item count / logits mode |
| 120 | u64 | Progress watchdog in device cycles, nonzero for EVALUATE |
| 128–255 | bytes | Zero |

Flag bit0 LAB_UNQUALIFIED permits an implemented but not yet qualified numerical profile/shape for tests; all results carry UNQUALIFIED. Normal applications leave it zero. The driver separately records test-mode authorization in its run manifest; this flag cannot bypass memory, range, safety or physical capability limits. No other flag is defined. Logits mode 0=last, 1=all, 2=selected strictly increasing position indices supplied by the input table, relative to this command. At least one output position is required.

Operation field rules (fields not named here must be zero, except magic/version/opcode/command ID):

| Operation | Fields used / checks |
|---|---|
| QUERY_CAPS | Command ID only |
| REGISTER_MODEL | profile, model/layout handles; idle; matching graph/config/packing/constants identities; freezes one active model |
| REGISTER_CONTEXT | profile, context ID/epoch, state/workspace handles, capacity; committed count initially zero; epoch nonzero; exact native/tiny state shapes |
| RESET_CONTEXT | context ID/current epoch, expected committed count; clear then atomically rebind all context-owned mutable registrations and context metadata to epoch+1; fails on u64 wrap; returns new epoch |
| EVALUATE | all defined fields except unused table handles may be zero only as explicitly allowed below; profile/model/layout must match registered values; state/workspace must match context; input/output required; expected count and first position match; capacity matches registration |
| CANCEL | own command ID, target command ID at offset40, target context and epoch; all other fields zero |

Command IDs are nonzero, strictly increasing **per mailbox** within a driver session. Separate monotonic counters for numerical and control commands avoid cancellation transport races. A control target identifies a numerical-mailbox ID, not another control request. No wrap/reuse: re-enumerate a new device session before exhausting u64. The driver allocates a new random 128-bit session nonce at attach and records it with every host result; kernel queues from earlier sessions are never adopted. Device reset requires new initialization and region generations. IDs and epochs detect stale results, but do not establish DMA quiescence.

Only one context is registered in ABI1. RESET_CONTEXT requires healthy transport and positive drain of numerical, host-service and copy engines. It clears all state/valid lengths and proposed positions while context is unavailable. Only after every clear completes, atomically publish count0, rope_delta0, new context epoch and the same new owner epoch for **every mutable region owned by that context**, including state, scratch, staging and output mappings. Handles/generations and immutable global regions do not change. This controlled reset rebind is the only in-place owner-epoch exception; no old transaction remains. The driver mirrors this metadata after acquiring reset success and before acknowledging/submitting another command. On failure, ownership/epoch metadata stays entirely old, context is invalid and no partial rebind is published, even though some data may be zeroed. A healthy drained device can retry the whole reset using that old epoch; fatal transport requires OFFLINE recovery. Reject stale old-epoch accesses after success. Check epoch wrap **before** clear/rebind. Context registration validates owner epochs then initializes zero state by the same clear/visibility rules without incrementing the supplied initial epoch. Runtime region registration/unregistration cannot remove a referenced state region to work around reset.

CANCEL acknowledges ACCEPTED, ALREADY_TERMINAL or NOT_FOUND using status 9/10/11. A repeated cancellation with a **new** control ID and same target is idempotent; a reused control ID is rejected as STALE_ID. CANCEL acknowledgement is not the target's terminal completion. Exactly one numerical terminal result exists: either a device completion after normal drain, or a host-origin fatal result when the device cannot respond. For ALREADY_TERMINAL the driver retains the last numerical ID/result until a newer command completes; older absent targets are NOT_FOUND. Host timeout never frees mappings on its own.

## 3. Completion: 64 bytes

Offsets 0/8/16/24 are u64 command ID/context ID/epoch/committed token count. Offsets32/36/40/44 are u32 status/opcode/failing layer/flags. Offsets48/56 are u64 elapsed device cycles/valid output bytes. Failing layer is 0xffffffff if none. Flags: bit0 CONTEXT_VALID, bit1 UNQUALIFIED; rest zero. On success, valid bytes equals the requested logits payload bytes. On any numerical failure valid output bytes=0, even if partial writes occurred. Before-mutation rejection can retain CONTEXT_VALID; after-mutation failure clears it. Full-command public commit occurs only after all outputs/state writes become visible; chunk barriers are internal.

Status: 0 SUCCESS, 1 BAD_DESCRIPTOR, 2 UNSUPPORTED, 3 CAPACITY, 4 NONFINITE, 5 TRANSPORT, 6 PROGRESS_TIMEOUT, 7 CANCELED, 8 BUSY, 9 CANCEL_ACCEPTED, 10 ALREADY_TERMINAL, 11 NOT_FOUND, 12 STALE_ID. Non-numerical success has valid output bytes=0. Context registration/reset returns the resulting context epoch/count. Query/model registration returns zero context/count. Command failure never fabricates a successful device result.

Driver-facing result envelope: `{session_nonce, origin:device|host, device_completion_present, command_id, status, context_valid, completion_bytes_or_null, recovery_evidence_id}`. Host-origin fatal status is `DEVICE_OFFLINE`, with no fabricated cycle count or completion. Driver retains the original terminal record if a late device completion arrives, logs it as late, and never publishes a second terminal result. The five-second normal-drain deadline and fatal quarantine rules in the implementation contract govern teardown.

## 4. Regions, handles and table schemas

A handle is `(generation << 32) | slot`, with nonzero 32-bit generation and slot 1..256. Slot generation advances on reuse; wrap retires the slot until a new device session. Zero means absent, never address zero. The registration table has at most 256 live regions. Trusted driver region records are 64 bytes:

| Offset | Type | Meaning |
|---|---|---|
| 0 | u64 | Handle |
| 8 / 12 | u32 each | Kind / permissions (bit0 read, bit1 write, adapter1 bit2 initialization-write) |
| 16 / 24 | u64 each | Base / byte length |
| 32 / 40 | u64 each | Owner context ID / epoch (zero for immutable model/global tables) |
| 48–63 | bytes | Zero |

Kinds 1 BOARD_DDR, 2 HOST_DMA, 3 MODEL_BYTES, 4 SIM_MEMORY. MODEL_BYTES base is a logical packed-file offset, not an IOVA, and is read-only; a checked host byte-range service fills credited staging buffers. BOARD_DDR uses a tested board aperture address. HOST_DMA uses a driver-produced device DMA address for **one contiguous DMA segment**. Scatter/gather consists of multiple registered segments; software must split transfers at segment boundaries and cannot pretend discontiguous addresses form one range. Reduce stage size when contiguous allocation is unavailable; inability to register the required number of regions fails admission. SIM_MEMORY is accepted only in simulation builds. TABLE pages use BOARD_DDR or SIM_MEMORY with read-only core access, driver sealed for the command/session lifetime. No HOST_DMA descriptor tables in ABI 1, avoiding live CPU mutation.

Permissions and lengths are fixed until drained/unregistered except adapter1’s one-way INIT_WRITE-to-READ seal; owner epochs change only through the atomic RESET_CONTEXT rule. Every nonempty interval must have a checked u64 end and fit its backing aperture/mapping/file length. Writable regions must be disjoint from **all** other registered regions; read-only aliases are allowed only for the same immutable backing object and bytes. The driver checks backing pages/board addresses, not merely different IOVAs. Table/constant/weight regions cannot alias writable outputs/state/scratch. Driver pin budget bounds HOST_DMA registrations. Owner/epoch checks apply to all mutable context regions; no physical reuse on epoch change until positive quiescence.

Each table starts with a 32-byte header: magic u32 `0x3142544c` (`LTB1`) at0, major u16=1 at4, kind u16 at6, entry_count u32 at8, entry_bytes u32 at12, total_bytes u64 at16, table_generation u64 at24. Generation is nonzero and must equal the containing region-handle generation. Exact total is `32+count*entry_bytes`, no trailing bytes within the registered table extent. Checked multiply/add precedes reads. Kind/schema limits:

| Kind | Entry bytes / count cap | Contents |
|---|---|---|
| 1 MODEL | 128 / 4096 | Tensor descriptors, exact active tensor inventory |
| 2 LAYOUT | 128 / 1 | Identity entry described below |
| 3 INPUT | 32 / 64 | Input-role entries |
| 4 STATE | 128 / 256 | Tensor descriptors for Delta/conv/KV/length/position metadata |
| 5 OUTPUT | 128 / 1 | One contiguous FP32 `[selected_positions,248320]` native logits tensor (tiny uses tiny V) |
| 6 WORKSPACE | 128 / 256 | Named tensor/scratch extents from the compiled liveness layout |
| 7 MEDIA | 64 / 16 | Media run descriptors referenced by INPUT |
| 8 INPUT_TENSORS | 128 / 64 | Sealed tensor-descriptor arena for INPUT/media indirection |

LAYOUT entry: model config SHA256 bytes0–31, packed-layout manifest SHA25632–63, numerical-kernel manifest SHA25664–95, constants SHA25696–127. These are raw digest bytes. Complete active tensor names/shapes/dtypes and layout IDs are frozen in the versioned packed-layout manifest; assign model tensor IDs 1..n by ascending UTF-8 tensor-name bytes. Packing/layout generation remains a D0 deliverable; missing manifest blocks model registration. STATE/WORKSPACE tensor IDs and exact logical axes come from the same layout manifest; do not infer them from arrival order. Registration checks the full expected set, no duplicates/missing/extra tensors. The model config digest alone does not authenticate tensor bytes; payload and packed hashes are separately mandatory in the manifest.

Tensor descriptor (128 bytes): tensor ID u32@0, rank u16@4, dtype u16@6, region handle u64@8, offset u64@16, extent u64@24, six dimensions u32@32, six byte strides u64@56, layout ID u32@104, flags u32@108=0, reserved16 bytes@112=0. Dtypes 1 BF16(2B), 2 F32(4B), 3 U32(4B), 4 I64(8B). Rank1..6; active dimensions positive; inactive dimensions/strides zero. Last-axis element strides may be padded but must be aligned and nonoverlapping: in outer-to-inner order each stride covers the full remaining inner span. Input tensor IDs equal their role number (all pixel descriptors use2 with item identity in INPUT); output tensor ID=1. Region offset/stride align to dtype; span=`dtype_bytes+sum((dim-1)*stride)` checked in u64 and <=extent; offset+extent<=region length. Tiled weight layouts require explicit manifest validation in addition to this span, not a fictitious dense stride view. Raw scratch can be rank1 U32 with aligned byte capacity.

INPUT entry (32 bytes): role u32@0, item_index u32@4, descriptor-table region handle u64@8, byte offset u64@16, element count u64@24. Roles1 TOKEN_IDS,2 NORMALIZED_PIXELS,3 MODALITY_TYPES,4 LOGIT_POSITION_INDICES point to a **128-byte TensorDescriptor entry inside a sealed kind8 INPUT_TENSORS table**, never raw data: offset must equal32+128*i for 0<=i<header.count, header/region generation must match and all128 bytes must be in the exact table extent. Resolve the descriptor, then its payload region/offset/extent separately. Element count equals the checked product of active descriptor dimensions, not bytes. Role5 MEDIA_TABLE points to offset0 of a complete sealed kind7 table and count equals that table header count. Reject a pointer into a header, middle of an entry, wrong kind, unsealed/stale table or raw payload region before writes. No implicit descriptor format is inferred from payload contents.

Roles1 and3 appear exactly once with item_index0: rank1 U32 arrays of T token IDs and modality types. Role4 appears exactly once with item_index0 only for selected logits, rank1 U32 strictly increasing indices in [0,T). Role5 appears exactly once with item_index0 only when run_count>0. Role2 has one rank4 BF16 `[F,3,H,W]` tensor per **distinct pixel item**, not per run. No duplicate roles/items or extras. Tokens are below vocabulary size; modality values0=text,1=image,2=video. Command field media_count at112 means **run_count** throughout ABI1; pixel_item_count is derived from distinct role2 entries. The count must agree with the MEDIA table. Pixel frame windows referenced by all runs fit the shared tensor, follow temporal repeat/sampling metadata and do not overlap for runs of one item. Selected-frame indices and timestamp text remain fixture provenance; already-tokenized timestamps are normal text.

MEDIA entry (64 bytes): item index u32@0; modality u32@4 (1/2); placeholder start u32@8 and length u32@12; temporal grid u32@16, height grid u32@20, width grid u32@24; first pixel frame u32@28; pixel frame count u32@32; temporal patch=2 u32@36; merge=2 u32@40; reserved u32@44=0; pixel tensor descriptor handle u64@48 and offset u64@56. Each entry is **one contiguous placeholder run/temporal grid entry** in the pinned processor's expanded prompt. For video with timestamp-separated runs, use separate media entries referring to the same pixel tensor with disjoint frame intervals; INPUT pixel roles index the distinct descriptor items. Thus command media count is the number of entries/runs, not distinct original files. Each run validates length=t*h*w/4, framecount=2*t, h/w even, marker/token/modality agreement, no overlapping runs, and pixel window bounds. Role2 appears exactly once per distinct pixel item_index used by MEDIA, at most16; multiple runs of the same video share that one pixel descriptor. Runtime segment cap is4, total raw patches<=1024, each segment<=256; admission counts temporal segments, not files. Fresh media only at committed=0. The whole-prompt position plan remains immutable across U1/U8 schedules.

Inside one writable scratch region, different live tensor views must not overlap. Explicit compiled liveness allows reuse after final consumer; this is sequencer behavior, not permission for caller-controlled aliases. State in-place Delta updates, conv ring replacement, KV append and elementwise scratch transforms are the only initial mutation classes, validated against that compiled manifest. Input/output regions are always disjoint. Reject collisions before execution; descriptor sealing prevents time-of-check/time-of-use mutation.

## 5. Capability record: 256 bytes

Offsets0 magic u32 `0x3150434c` (`LCP1`);4 major u16=1;6 record size u16=256. Offsets8 opcode bitmask u64 (bits0..5 only);16 implemented profile bitmask u32;20 qualified profile bitmask u32. Offsets24/28 context allocated/qualified maxima u32;32/36 prompt allocated/qualified maxima u32;40 segment maximum u32;44 patches/segment u32;48 total patches u32;52 max region count u32;56 core beat bytes u32;60 core clock Hz u32 (simulation may use0). Offsets64/96/128/160 contain config/layout/kernel/constants SHA256 raw bytes. Offset192 session nonce16 bytes (written by trusted attach initialization, read-only thereafter);208 max registered DMA/pin bytes u64;216 max table entries u32=4096;220 completion size u32=64;224 command size u32=256;228 reserved u32=0;232..255zero.

Implementation profiles and dimensions are constraints, not proof. A profile's qualified bit is set only after all required fidelity fixtures for the advertised qualified dimensions pass; otherwise zero. Prompt/context maxima cannot alone express modality qualification: default media use requires D8 suite qualification in the immutable bitstream/run manifest matching all four digests. LAB_UNQUALIFIED test runs explicitly report unqualified status. Claiming configured262144 context in an allocated4096 implementation is forbidden. Core checks command bounds even when driver checked them.

## 6. Required interface tests

Freeze byte-level positive command/table/region/completion fixtures and independently decode them. Check >4-GiB offsets, malformed exact lengths, unsupported opcode6, all reserved fields, stale IDs/generations/epochs, missing roles, bad strides/spans, overflow, physical aliases, sealed-table modification, mismatched digests, unauthenticated registration, capacity/logits allocation, cancel while busy, repeated cancel and result-slot backpressure. Planning codec checks cover encoding/bounds examples; RTL/driver conformance and fatal isolation remain implementation gates. Do not describe Python codec tests as a working PCIe interface.

A complete byte-level four-run video input and EVALUATE command are in [abi-lifecycle-example.json](abi-lifecycle-example.json), generated/checked by `abi_v1.py` and `refinement_checks.py`. It states model/context-registration prerequisites and encodes every input/media/output descriptor; it does not substitute for implemented parser/transport qualification.
