"""Repeatable planning checks; does not claim model/RTL/driver qualification."""
import argparse, hashlib, json, pathlib, shutil, struct, tempfile
import abi_v1 as abi
from plan_audit_checks import verify_sources

ROOT=pathlib.Path(__file__).resolve().parent
FIXTURE_SHA256='1246dcac859fa2fa3f6d05c0b91bc3595e2185a022c6694d6d1b25fe67f5b9a2'

def must_reject(action):
    try: action()
    except (ValueError, FileNotFoundError): return True
    raise AssertionError('invalid case unexpectedly accepted')

def f32(x): return struct.unpack('<f',struct.pack('<f',x))[0]

def run():
    source=ROOT/'reference-sources'; lock=ROOT/'reference-source-lock.json'
    verified=verify_sources(source,lock)
    negatives=[]
    with tempfile.TemporaryDirectory(prefix='qwen-plan-check-') as td:
        root=pathlib.Path(td)
        for case in ('mutated_helper','missing_processor','unexpected_file','mutated_lock'):
            dest=root/case; shutil.copytree(source,dest)
            copied_lock=root/(case+'.json'); shutil.copy2(lock,copied_lock)
            if case=='mutated_helper':
                p=next(dest.glob('*vision_utils*')); p.write_bytes(p.read_bytes()+b'\n# changed\n')
            elif case=='missing_processor': next(dest.glob('*processing_qwen3_vl*')).unlink()
            elif case=='unexpected_file': (dest/'unlocked.py').write_text('pass\n')
            else: copied_lock.write_bytes(copied_lock.read_bytes()+b' ')
            assert must_reject(lambda:verify_sources(dest,copied_lock)); negatives.append(case)
    verify_sources(source,lock)
    fixture_bytes=(ROOT/'qualification-fixtures.json').read_bytes()
    if hashlib.sha256(fixture_bytes).hexdigest()!=FIXTURE_SHA256:
        raise ValueError('Fixture recipes/ceilings changed: version and independently review before acceptance')
    fx=json.loads(fixture_bytes)
    assert len(fx['calibration'])==8 and len(fx['holdout'])==16
    ids=[]
    for group in ('calibration','holdout'):
        for fixture in fx[group]:
            s=fixture['seed']; expected=[]
            for _ in range(fixture['length']):
                s=(1664525*s+1013904223)&0xffffffff; expected.append(1000+s%199000)
            assert expected==fixture['token_ids']
            ids.append(fixture['id'])
            assert all(0<=p<fixture['length'] for p in fixture['compare_positions'])
    assert len(set(ids))==24
    assert not {x['seed'] for x in fx['calibration']} & {x['seed'] for x in fx['holdout']}
    assert fx['version']==2 and len(fx['semantic_text'])==6 and len(fx['stress_text'])==4
    for split,expected in (('calibration',12),('holdout',22)):
        assert len(fx[split])+sum(x['split']==split for x in fx['semantic_text']+fx['stress_text'])==expected
        assert sum(x['split']==split for x in fx['media'])==4
    assert len({x['id'] for x in fx['semantic_text']+fx['stress_text']+fx['media']})==18
    assert all('all full-prompt positions' in x['compare_positions'] and x['state_checkpoints'] for x in fx['media'])
    # Independently expected offsets, rather than round-trip alone.
    query=abi.pack_command(command_id=1)
    assert query[:24].hex()=='4c4c4d310100000000000000000000000100000000000000'
    cancel=abi.pack_command(opcode=5,command_id=2,context_id=7,epoch=3,expected_or_target=99)
    assert struct.unpack_from('<Q',cancel,40)[0]==99 and struct.unpack_from('<H',cancel,6)[0]==5
    assert abi.unpack_command(cancel)['context_id']==7
    invalid={
        'generation_opcode_disabled':lambda:abi.pack_command(opcode=6,command_id=3),
        'missing_cancel_target':lambda:abi.pack_command(opcode=5,command_id=3,context_id=7,epoch=3),
        'reserved_bytes':lambda:abi.unpack_command(query[:-1]+b'\x01'),
        'unknown_flag':lambda:abi.pack_command(command_id=3,flags=2),
        'bad_handle_generation':lambda:abi.handle(1,0),
        'range_overflow':lambda:abi.checked_end(abi.U64-1,4),
        'inapplicable_payload':lambda:abi.pack_command(command_id=3,new_tokens=1),
    }
    table=abi.pack_table(3,1,[bytes(32)])
    assert table[:32].hex()=='4c54423101000300010000002000000040000000000000000100000000000000'
    assert abi.unpack_table(table,1)[0]==3
    invalid.update(table_truncated=lambda:abi.unpack_table(table[:-1],1),
                   table_extra=lambda:abi.unpack_table(table+b'\0',1),
                   table_wrong_generation=lambda:abi.unpack_table(table,2))
    regions=[dict(backing_object='page0',start=0,length=4096,permissions=1),
             dict(backing_object='page0',start=2048,length=4096,permissions=3)]
    invalid['physical_alias']=lambda:abi.validate_backing_aliases(regions)
    tracker=abi.IdTracker(); tracker.accept('command',4); tracker.accept('control',1)
    invalid['reused_command_id']=lambda:tracker.accept('command',4)
    for action in invalid.values(): assert must_reject(action)
    reg=abi.pack_region(abi.handle(1,1),2,3,0x100002000,4096,7,3)
    assert len(reg)==64 and struct.unpack_from('<Q',reg,16)[0]==0x100002000
    video=abi.video_lifecycle_example()
    tables={int(k):bytes.fromhex(v) for k,v in video['tables_hex'].items()}
    _,entries=abi.unpack_table(tables[abi.handle(2,1)],1)
    for entry in entries: abi.resolve_input_pointer(entry,tables,set(tables))
    command=abi.unpack_command(bytes.fromhex(video['command_hex']))
    assert command['media_count']==4 and command['new_tokens']==264
    _,runs=abi.unpack_table(tables[abi.handle(3,1)],1)
    for i,run in enumerate(runs):
        f=abi.MEDIA.unpack(run)
        assert f[:12]==(0,2,66*i+1,64,1,16,16,2*i,2,2,2,0)
        assert f[12:]==(abi.handle(1,1),160)
        assert video['payloads']['token_ids'][66*i:66*(i+1)]==[248053]+[248057]*64+[248054]
    malformed_pointers={
       'header_pointer':abi.INPUT.pack(1,0,abi.handle(1,1),0,264),
       'mid_entry_pointer':abi.INPUT.pack(1,0,abi.handle(1,1),40,264),
       'outside_arena_pointer':abi.INPUT.pack(1,0,abi.handle(1,1),416,264),
       'wrong_table_kind':abi.INPUT.pack(1,0,abi.handle(3,1),32,264),
       'wrong_element_count':abi.INPUT.pack(1,0,abi.handle(1,1),32,263),
       'stale_pointer_generation':abi.INPUT.pack(1,0,abi.handle(1,2),32,264)}
    for entry in malformed_pointers.values():
        assert must_reject(lambda:abi.resolve_input_pointer(entry,tables,set(tables)))
    assert must_reject(lambda:abi.resolve_input_pointer(entries[0],tables,set()))
    reset=abi.reset_metadata(3,[3,3,3,3]); assert reset['epoch']==4 and reset['owners']==[4]*4
    failed=abi.reset_metadata(4,[4]*4,clear_ok=False)
    assert failed['epoch']==4 and failed['owners']==[4]*4 and not failed['context_valid']
    assert abi.reset_metadata(failed['epoch'],failed['owners'])['epoch']==5
    for call in (lambda:abi.reset_metadata(4,[3]*4),lambda:abi.reset_metadata(abi.U64,[abi.U64]),
                 lambda:abi.reset_metadata(4,[4],drained=False),lambda:abi.reset_metadata(4,[4],healthy=False)):
        assert must_reject(call)
    a,b,c=1+2**-23,1-2**-23,-1
    separate=f32(f32(a*b)+c); fused=f32(a*b+c)
    assert separate==0 and fused==-(2**-46) # chosen products exact in binary64, not a generic FMA oracle
    ordered=f32(f32(f32(1e20)+f32(-1e20))+3)
    reassociated=f32(f32(1e20)+f32(f32(-1e20)+3))
    assert ordered==3 and reassociated==0
    body=24350556160; head=1271398400; n=256; e=1152; j=4304; layers=27; m=64
    vision_dense=layers*n*(4*e*e+2*e*j)
    vision_attn=layers*4*n*n*e # three QK passes plus AV
    patch=n*e*1536; merger=m*((4*e)**2+(4*e)*5120)
    vision=vision_dense+vision_attn+patch+merger
    workloads={'D7_one_token':body+head,'D7_prompt8_decode8':16*body+9*head,
               'D8_decoder_last_head':66*body+head,'D8_vision_subtotal':vision,
               'D8_combined_subtotal':66*body+head+vision,
               'D8_all_position_head_subtotal':66*(body+head)+vision}
    runtime={k:{'macs':v,'ideal_cycles_8lanes':v/8,
                'days_at_cycles_per_second':{str(rate):v/8/rate/86400 for rate in (10000,100000,1000000)}}
             for k,v in workloads.items()}
    return {'status':'PASS: planning checks only','immutable_source_check':verified,
            'negative_source_tests':negatives,'fixed_random_text_fixtures':len(ids),
            'additional_fixed_fixtures':{'semantic_recipes_pending_tokenization':6,'stress_token_sequences':4},
            'media_recipe_count':8,'input_pointer_negative_cases':list(malformed_pointers)+['unsealed_arena'],
            'reset_contract_checks':'atomic owner epoch update; failed clear retains old metadata; retry; stale owner; wrap; undrained/unhealthy rejection; no physical-reset implementation',
            'video_lifecycle_example':video,
            'abi_negative_cases':list(invalid),'abi_examples':abi.examples(),
            'arithmetic_directed':{'fma_fused':fused,'mul_add_separate':separate,
                                   'sum_ordered':ordered,'sum_reassociated':reassociated},
            'runtime_lower_bounds':runtime,
            'runtime_omissions':'text attention, Delta/vector/norm/nonlinear work, memory/control stalls, preprocessing; no measured simulator rate',
            'artifact_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in
                               ('qualification-fixtures.json','abi-v1.md','adapter-v1.md','abi_v1.py','implementation-contract.md')}}

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--out',default=str(ROOT/'refinement-checks.json')); args=p.parse_args()
    result=run(); pathlib.Path(args.out).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    (ROOT/'abi-lifecycle-example.json').write_text(json.dumps(result['video_lifecycle_example'],indent=2)+'\n',encoding='utf-8')
    print(result['status'])
