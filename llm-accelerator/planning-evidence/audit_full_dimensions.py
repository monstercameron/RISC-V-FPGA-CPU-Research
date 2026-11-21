"""Static dimension ledger for all learned tensors in the active inference graph.
Derived from saved config + inspected implementation. No checkpoint tensor inventory.
"""
import json,math,hashlib
from pathlib import Path
base=Path(__file__).parent
c=json.loads((base/'qwen-config.json').read_text()); t=c['text_config'];v=c['vision_config']
H,I,V=t['hidden_size'],t['intermediate_size'],t['vocab_size']
L=t['num_hidden_layers']; A=t['layer_types'].count('full_attention'); R=L-A
Q,K,D=t['num_attention_heads'],t['num_key_value_heads'],t['head_dim']
KH,VH,DK,DV=t['linear_num_key_heads'],t['linear_num_value_heads'],t['linear_key_head_dim'],t['linear_value_head_dim']
C=2*KH*DK+VH*DV; VD=VH*DV; W,J,HEADS=v['hidden_size'],v['intermediate_size'],v['num_heads']; M=v['spatial_merge_size']**2; F=W*M
rows=[]
def add(name,shape,count=1): rows.append(dict(name=name,shape=shape,count=count,elements_each=math.prod(shape),elements_total=math.prod(shape)*count))
add('text.embedding',[V,H]);add('text.lm_head',[V,H]);add('text.final_norm.weight',[H])
add('decoder.input_norm.weight',[H],L);add('decoder.post_mixer_norm.weight',[H],L)
for name,shape in [('gate',[I,H]),('up',[I,H]),('down',[H,I])]:add('ffn.'+name,shape,L)
for name,shape in [('q_and_gate',[2*Q*D,H]),('k',[K*D,H]),('v',[K*D,H]),('out',[H,Q*D]),('q_norm',[D]),('k_norm',[D])]:add('full_attention.'+name,shape,A)
for name,shape in [('qkv',[C,H]),('z',[VD,H]),('a',[VH,H]),('b',[VH,H]),('out',[H,VD]),('conv.weight',[C,1,t['linear_conv_kernel_dim']]),('dt_bias',[VH]),('A_log',[VH]),('gated_norm.weight',[DV])]:add('delta.'+name,shape,R)
add('vision.patch.weight',[W,v['in_channels'],v['temporal_patch_size'],v['patch_size'],v['patch_size']]);add('vision.patch.bias',[W]);add('vision.position_table',[v['num_position_embeddings'],W])
for name,shape in [('norm1.weight',[W]),('norm1.bias',[W]),('norm2.weight',[W]),('norm2.bias',[W]),('qkv.weight',[3*W,W]),('qkv.bias',[3*W]),('out.weight',[W,W]),('out.bias',[W]),('fc1.weight',[J,W]),('fc1.bias',[J]),('fc2.weight',[W,J]),('fc2.bias',[W])]:add('vision.block.'+name,shape,v['depth'])
for name,shape in [('norm.weight',[W]),('norm.bias',[W]),('fc1.weight',[F,F]),('fc1.bias',[F]),('fc2.weight',[H,F]),('fc2.bias',[H])]:add('vision.merger.'+name,shape)
assert Q%K==0 and VH%KH==0 and W%HEADS==0
assert len(t['layer_types'])==L and H==v['out_hidden_size']
assert int(D*t['partial_rotary_factor'])%2==0
assert len(t['rope_parameters']['mrope_section'])==3
assert sum(t['rope_parameters']['mrope_section'])==int(D*t['partial_rotary_factor'])//2
assert math.isqrt(v['num_position_embeddings'])**2==v['num_position_embeddings']
text_params=sum(r['elements_total'] for r in rows if not r['name'].startswith('vision.'))
vision_params=sum(r['elements_total'] for r in rows if r['name'].startswith('vision.'))
report=dict(config_sha256=hashlib.sha256((base/'qwen-config.json').read_bytes()).hexdigest(),
            implementation_sha256=hashlib.sha256((base/'modeling_qwen3_5.py').read_bytes()).hexdigest(),
            dimensions=dict(H=H,I=I,V=V,L=L,delta_layers=R,attention_layers=A,query_width=Q*D,kv_width=K*D,
                            q_gate_width=2*Q*D,delta_qkv_width=C,delta_value_width=VD,gqa_group=Q//K,
                            delta_repeat=VH//KH,rotary_dim=int(D*t['partial_rotary_factor']),
                            vision_width=W,vision_heads=HEADS,vision_head_dim=W//HEADS,
                            vision_patch_flat=v['in_channels']*v['temporal_patch_size']*v['patch_size']**2,
                            vision_ffn=J,vision_layers=v['depth'],vision_merged_width=F),
            parameter_elements=dict(text=text_params,vision=vision_params,total=text_params+vision_params),
            bf16_bytes=dict(text=2*text_params,vision=2*vision_params,total=2*(text_params+vision_params)),
            state_bytes=dict(delta_fp32=R*VH*DK*DV*4,conv_bf16=R*C*t['linear_conv_kernel_dim']*2,
                             kv_bf16_per_token=A*2*K*D*2),
            tensors=rows,exclusions=['MTP training/speculation auxiliary weights','optimizer/training state','nonpersistent analytic buffers'])
(base/'full-dimension-audit.json').write_text(json.dumps(report,indent=2)+'\n')
md=['# Full forward-pass dimension ledger','', 'Constructor-derived active tensor inventory, independently reconciled against all checkpoint shard keys/shapes by verify_checkpoint_shapes.py (see checkpoint-shape-audit.json). See plan.md for execution semantics.','',
    '| Learned tensor family | Shape (checkpoint output-first) | Multiplicity | Total elements |','|---|---|---:|---:|']
for r in rows:md.append('| '+r['name']+' | '+' x '.join(map(str,r['shape']))+' | '+str(r['count'])+' | '+f"{r['elements_total']:,}"+' |')
md+=['','Text parameters: '+f'{text_params:,}', 'Vision parameters: '+f'{vision_params:,}', 'Active-graph total: '+f'{text_params+vision_params:,}', '',
     'These totals include biases and normalization parameters and exclude auxiliary MTP. The separate checkpoint-shape-audit.json classifies all 15 auxiliary MTP tensors and reconciles total payload bytes. Actual tensor data loading and packed-layout verification remain implementation work.']
(base/'dimension-ledger.md').write_text('\n'.join(md)+'\n')
print(json.dumps({k:report[k] for k in ['dimensions','parameter_elements','bf16_bytes','state_bytes']},indent=2))
