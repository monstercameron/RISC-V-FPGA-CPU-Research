"""Independent exact-name/shape check against fetched safetensors headers."""
import json,math
from pathlib import Path
b=Path(__file__).parent;c=json.loads((b/'qwen-config.json').read_text());t=c['text_config'];v=c['vision_config']
actual={k:d for p in (b/'qwen-headers').glob('*.json') for k,d in json.loads(p.read_text()).items() if k!='__metadata__'}
index=json.loads((b/'qwen-weight-index.json').read_text())
assert set(actual)==set(index['weight_map'])
expected={}
def put(k,*s):expected[k]=list(s)
H,I,V=t['hidden_size'],t['intermediate_size'],t['vocab_size'];Q,D,K=t['num_attention_heads'],t['head_dim'],t['num_key_value_heads']
C=2*t['linear_num_key_heads']*t['linear_key_head_dim']+t['linear_num_value_heads']*t['linear_value_head_dim'];VD=t['linear_num_value_heads']*t['linear_value_head_dim']
put('lm_head.weight',V,H);put('model.language_model.embed_tokens.weight',V,H);put('model.language_model.norm.weight',H)
def mlp(p):
    for key,s in [('gate_proj',(I,H)),('up_proj',(I,H)),('down_proj',(H,I))]:put(p+'.mlp.'+key+'.weight',*s)
def att(p):
    for key,s in [('q_proj',(2*Q*D,H)),('k_proj',(K*D,H)),('v_proj',(K*D,H)),('o_proj',(H,Q*D)),('q_norm',(D,)),('k_norm',(D,))]:put(p+'.self_attn.'+key+'.weight',*s)
for l,kind in enumerate(t['layer_types']):
    p=f'model.language_model.layers.{l}'
    put(p+'.input_layernorm.weight',H);put(p+'.post_attention_layernorm.weight',H);mlp(p)
    if kind=='full_attention':att(p)
    else:
        for key,s in [('in_proj_qkv.weight',(C,H)),('in_proj_z.weight',(VD,H)),('in_proj_a.weight',(t['linear_num_value_heads'],H)),('in_proj_b.weight',(t['linear_num_value_heads'],H)),('out_proj.weight',(H,VD)),('conv1d.weight',(C,1,t['linear_conv_kernel_dim'])),('A_log',(t['linear_num_value_heads'],)),('dt_bias',(t['linear_num_value_heads'],)),('norm.weight',(t['linear_value_head_dim'],))]:put(p+'.linear_attn.'+key,*s)
E,J=v['hidden_size'],v['intermediate_size'];F=E*v['spatial_merge_size']**2
put('model.visual.patch_embed.proj.weight',E,v['in_channels'],v['temporal_patch_size'],v['patch_size'],v['patch_size']);put('model.visual.patch_embed.proj.bias',E);put('model.visual.pos_embed.weight',v['num_position_embeddings'],E)
for l in range(v['depth']):
    p=f'model.visual.blocks.{l}'
    for key,o,i in [('attn.qkv',3*E,E),('attn.proj',E,E),('mlp.linear_fc1',J,E),('mlp.linear_fc2',E,J)]:put(p+'.'+key+'.weight',o,i);put(p+'.'+key+'.bias',o)
    for key in ['norm1','norm2']:put(p+'.'+key+'.weight',E);put(p+'.'+key+'.bias',E)
for key,o,i in [('linear_fc1',F,F),('linear_fc2',H,F)]:put('model.visual.merger.'+key+'.weight',o,i);put('model.visual.merger.'+key+'.bias',o)
put('model.visual.merger.norm.weight',E);put('model.visual.merger.norm.bias',E)
active=set(expected)
# Separate auxiliary MTP inventory: present in the checkpoint, not called by ordinary forward.
put('mtp.fc.weight',H,2*H)
for key in ['norm','pre_fc_norm_embedding','pre_fc_norm_hidden']:put('mtp.'+key+'.weight',H)
put('mtp.layers.0.input_layernorm.weight',H);put('mtp.layers.0.post_attention_layernorm.weight',H);mlp('mtp.layers.0');att('mtp.layers.0')
missing=sorted(set(expected)-set(actual));unexpected=sorted(set(actual)-set(expected))
mismatches={k:dict(expected=s,actual=actual[k]['shape']) for k,s in expected.items() if k in actual and s!=actual[k]['shape']}
assert not missing and not unexpected and not mismatches,(missing,unexpected,mismatches)
assert all(x['dtype']=='BF16' for x in actual.values())
for key,x in actual.items():assert x['data_offsets'][1]-x['data_offsets'][0]==2*math.prod(x['shape']),key
active_elements=sum(math.prod(actual[k]['shape']) for k in active)
aux_elements=sum(math.prod(x['shape']) for k,x in actual.items() if k not in active)
total_bytes=2*(active_elements+aux_elements)
assert total_bytes==int(index['metadata']['total_size'])
derived=json.loads((b/'full-dimension-audit.json').read_text())
assert active_elements==derived['parameter_elements']['total']
report=dict(shards=18,tensors_total=len(actual),active_tensors=len(active),auxiliary_mtp_tensors=len(actual)-len(active),
            active_elements=active_elements,auxiliary_mtp_elements=aux_elements,total_elements=active_elements+aux_elements,
            active_bytes=2*active_elements,auxiliary_mtp_bytes=2*aux_elements,total_bytes=total_bytes,
            dtypes=['BF16'],missing=missing,unexpected=unexpected,shape_mismatches=mismatches,
            checkpoint_weights_downloaded=False,method='Bounded HTTP range reads of JSON headers only; every tensor key, shape, dtype and byte span checked.')
(b/'checkpoint-shape-audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
