"""ABI-1 planning codec: byte layouts/bounds examples, not a driver or RTL model."""
import struct

U64 = (1 << 64) - 1
COMMAND_FIELDS = (
    ('magic','I'), ('major','H'), ('opcode','H'), ('flags','I'), ('profile','I'),
    ('command_id','Q'), ('context_id','Q'), ('epoch','Q'), ('expected_or_target','Q'),
    ('model','Q'), ('layout','Q'), ('input','Q'), ('state','Q'), ('output','Q'),
    ('workspace','Q'), ('first_position','Q'), ('new_tokens','I'), ('capacity','I'),
    ('media_count','I'), ('logits_mode','I'), ('watchdog','Q'))
COMMAND = struct.Struct('<' + ''.join(fmt for _, fmt in COMMAND_FIELDS))
TABLE = struct.Struct('<IHHIIQQ')
REGION = struct.Struct('<QIIQQQQ16s')
COMPLETION = struct.Struct('<QQQQIIIIQQ')
TABLE_SCHEMAS = {1:(128,4096),2:(128,1),3:(32,64),4:(128,256),
                 5:(128,1),6:(128,256),7:(64,16),8:(128,64)}

def checked_end(base, size):
    if not (0 <= base <= U64 and 0 < size <= U64 and base <= U64-size):
        raise ValueError('invalid/overflowing range')
    return base + size

def handle(slot, generation):
    if not (1 <= slot <= 256 and 1 <= generation < (1 << 32)):
        raise ValueError('invalid handle')
    return (generation << 32) | slot

def validate_handle(value):
    return handle(value & 0xffffffff, value >> 32)

def pack_command(**kwargs):
    if set(kwargs) - {n for n,_ in COMMAND_FIELDS}:
        raise ValueError('unknown field')
    fields = {n:0 for n,_ in COMMAND_FIELDS}
    fields.update(magic=0x314d4c4c, major=1)
    fields.update(kwargs)
    try:
        raw = COMMAND.pack(*(fields[n] for n,_ in COMMAND_FIELDS)) + bytes(128)
    except struct.error as e:
        raise ValueError(str(e)) from e
    unpack_command(raw)
    return raw

def unpack_command(raw):
    if len(raw) != 256 or any(raw[128:]):
        raise ValueError('length/reserved bytes')
    f = dict(zip((n for n,_ in COMMAND_FIELDS), COMMAND.unpack(raw[:128])))
    if f['magic'] != 0x314d4c4c or f['major'] != 1 or f['opcode'] not in range(6):
        raise ValueError('unsupported protocol/opcode')
    if f['command_id'] == 0 or f['flags'] & ~1 or f['profile'] not in (0,1):
        raise ValueError('ID/flags/profile')
    common = {'magic','major','opcode','command_id'}
    allowed = {0:set(),1:{'profile','model','layout'},
               2:{'profile','context_id','epoch','state','workspace','capacity'},
               3:{'context_id','epoch','expected_or_target'},
               4:set(f)-common,5:{'context_id','epoch','expected_or_target'}}[f['opcode']]
    if any(v for k,v in f.items() if k not in common|allowed):
        raise ValueError('operation-inapplicable field')
    for n in ('model','layout','input','state','output','workspace'):
        if f[n]: validate_handle(f[n])
    if f['opcode'] == 1 and not (f['model'] and f['layout']):
        raise ValueError('missing model registration tables')
    if f['opcode'] in (2,3,4,5) and not (f['context_id'] and f['epoch']):
        raise ValueError('missing context identity')
    if f['opcode'] == 2 and not (f['state'] and f['workspace'] and f['capacity']):
        raise ValueError('missing context registration')
    if f['opcode'] == 4:
        if not all(f[n] for n in ('model','layout','input','state','output','workspace','new_tokens','capacity','watchdog')):
            raise ValueError('missing evaluation field')
        if f['first_position'] != f['expected_or_target'] or f['logits_mode'] > 2:
            raise ValueError('position/logits mode')
        if checked_end(f['first_position'],f['new_tokens']) > f['capacity']:
            raise ValueError('capacity')
        if f['media_count'] > 16 or (f['media_count'] and f['first_position']):
            raise ValueError('media append/count')
    if f['opcode'] == 5 and not f['expected_or_target']:
        raise ValueError('missing cancellation target')
    return f

def pack_table(kind, generation, entries):
    if kind not in TABLE_SCHEMAS: raise ValueError('table kind')
    size, cap = TABLE_SCHEMAS[kind]
    if not (0 < generation < (1 << 32) and 0 < len(entries) <= cap):
        raise ValueError('count/generation')
    if any(len(e) != size for e in entries): raise ValueError('entry size')
    return TABLE.pack(0x3142544c,1,kind,len(entries),size,32+size*len(entries),generation)+b''.join(entries)

def unpack_table(raw, region_generation):
    if len(raw) < 32: raise ValueError('short table')
    magic, major, kind, count, size, total, gen = TABLE.unpack(raw[:32])
    if magic != 0x3142544c or major != 1 or kind not in TABLE_SCHEMAS:
        raise ValueError('table protocol')
    esize, cap = TABLE_SCHEMAS[kind]
    if size != esize or not (0 < count <= cap) or total != 32+count*size or total != len(raw):
        raise ValueError('table length/count')
    if gen != region_generation or not 0 < gen < 1 << 32:
        raise ValueError('table generation')
    return kind, [raw[32+i*size:32+(i+1)*size] for i in range(count)]

def pack_region(region_handle, kind, permissions, base, length, owner=0, epoch=0):
    validate_handle(region_handle)
    if kind not in (1,2,3,4) or permissions not in (1,2,3,5): raise ValueError('kind/permissions')
    if permissions == 5 and kind not in (1,4): raise ValueError('initialization permission kind')
    if kind == 3 and permissions != 1: raise ValueError('mutable model bytes')
    if bool(owner) != bool(epoch): raise ValueError('owner epoch')
    checked_end(base,length)
    return REGION.pack(region_handle,kind,permissions,base,length,owner,epoch,bytes(16))

def validate_backing_aliases(records):
    """Records use resolved backing_object, start, length, permissions (not IOVA)."""
    for i,a in enumerate(records):
        ae=checked_end(a['start'],a['length'])
        for b in records[:i]:
            be=checked_end(b['start'],b['length'])
            if a['backing_object']==b['backing_object'] and a['start']<be and b['start']<ae:
                if (a['permissions']|b['permissions']) & 6:
                    raise ValueError('writable backing alias')

class IdTracker:
    def __init__(self): self.last={'command':0,'control':0}
    def accept(self, mailbox, command_id):
        if mailbox not in self.last or not self.last[mailbox] < command_id <= U64:
            raise ValueError('stale/reused ID')
        self.last[mailbox]=command_id

def examples():
    query=pack_command(command_id=1)
    cancel=pack_command(opcode=5,command_id=2,context_id=7,epoch=3,expected_or_target=99)
    region=pack_region(handle(1,1),2,3,0x100002000,4096,7,3)
    table=pack_table(3,1,[struct.pack('<IIQQQ',1,0,handle(1,1),32,264)])
    return {'scope':'byte encoding examples; see abi-lifecycle-example.json for all linked video input tables',
            'query_hex':query.hex(),'cancel_hex':cancel.hex(),'region_above_4g_hex':region.hex(),
            'table_header_hex':table[:32].hex(),
            'completion_hex':COMPLETION.pack(99,7,3,0,7,4,0xffffffff,0,123,0).hex()}

TENSOR=struct.Struct('<IHHQQQ6I6QII16s')
INPUT=struct.Struct('<IIQQQ')
MEDIA=struct.Struct('<12I2Q')

def pack_tensor(tensor_id,dtype,region,dims):
    sizes={1:2,2:4,3:4,4:8}
    if dtype not in sizes or not 1<=len(dims)<=6 or any(d<=0 for d in dims): raise ValueError('tensor shape')
    strides=[]; extent=sizes[dtype]
    for d in reversed(dims): strides.insert(0,extent); extent*=d
    if extent>U64: raise ValueError('tensor overflow')
    return TENSOR.pack(tensor_id,len(dims),dtype,region,0,extent,
                       *(list(dims)+[0]*(6-len(dims))),*(strides+[0]*(6-len(dims))),0,0,bytes(16))

def resolve_input_pointer(entry,tables,sealed):
    role,item,region,offset,count=INPUT.unpack(entry)
    if region not in sealed or region not in tables: raise ValueError('unsealed/missing pointer target')
    kind,entries=unpack_table(tables[region],region>>32)
    if role==5:
        if kind!=7 or offset!=0 or count!=len(entries): raise ValueError('media table pointer')
        return entries
    if role not in (1,2,3,4) or kind!=8 or offset<32 or (offset-32)%128:
        raise ValueError('tensor descriptor pointer')
    index=(offset-32)//128
    if index>=len(entries): raise ValueError('descriptor pointer out of range')
    values=TENSOR.unpack(entries[index]); rank=values[1]; dims=values[6:12]
    if not 1<=rank<=6: raise ValueError('rank')
    elements=1
    for d in dims[:rank]: elements*=d
    if not count==elements or not 0<elements<=U64: raise ValueError('input element count')
    if values[0]!=role: raise ValueError('tensor role identity')
    return values

def reset_metadata(epoch, owner_epochs, *, drained=True, healthy=True, clear_ok=True):
    """Contract oracle for metadata publication, with no DMA or physical clear implementation."""
    if not drained or not healthy: raise ValueError('reset needs healthy quiescence')
    if not 0<epoch<U64 or any(e!=epoch for e in owner_epochs): raise ValueError('stale/wrapped ownership')
    if not clear_ok: return {'epoch':epoch,'owners':list(owner_epochs),'context_valid':False}
    return {'epoch':epoch+1,'owners':[epoch+1]*len(owner_epochs),'context_valid':True,'committed':0,'rope_delta':0}

def video_lifecycle_example():
    """Fully specified command/input byte fixture; model/state registration is a precondition."""
    h=lambda n:handle(n,1)
    tokens=([248053]+[248057]*64+[248054])*4
    modalities=([0]+[2]*64+[0])*4
    pixels=8*3*256*256
    arena=pack_table(8,1,[pack_tensor(1,3,h(10),[264]),
                         pack_tensor(2,1,h(11),[8,3,256,256]),
                         pack_tensor(3,3,h(12),[264])])
    runs=[MEDIA.pack(0,2,66*i+1,64,1,16,16,2*i,2,2,2,0,h(1),160) for i in range(4)]
    media=pack_table(7,1,runs)
    input_entries=[INPUT.pack(1,0,h(1),32,264),INPUT.pack(2,0,h(1),160,pixels),
                   INPUT.pack(3,0,h(1),288,264),INPUT.pack(5,0,h(3),0,4)]
    inputs=pack_table(3,1,input_entries)
    output=pack_table(5,1,[pack_tensor(1,2,h(13),[1,248320])])
    tables={h(1):arena,h(2):inputs,h(3):media,h(4):output}
    for entry in input_entries: resolve_input_pointer(entry,tables,set(tables))
    cmd=pack_command(opcode=4,command_id=17,context_id=7,epoch=3,profile=1,flags=1,
                     model=h(6),layout=h(7),input=h(2),state=h(5),output=h(4),workspace=h(8),
                     first_position=0,expected_or_target=0,new_tokens=264,capacity=4096,
                     media_count=4,logits_mode=0,watchdog=100000000)
    events=[
       'INIT_SESSION nonce 00112233445566778899aabbccddeeff; session ready',
       'Register HOST_DMA segments and DDR tables; COPY initialized bytes; SEAL tables/inputs',
       'REGISTER_MODEL handles6/7 and REGISTER_CONTEXT7 epoch3 handles5/8; zero state completes',
       'EVALUATE17 epoch3; full 264-position plan created before U1 chunks',
       'Weight request1: MODEL_BYTES handle20 offset4294971392 length8192 -> stageA handle21 offset0',
       'COPY1 HOST_DMA handle30 offset0 length4096 -> stageA offset0; visible completion',
       'COPY2 noncontiguous HOST_DMA handle31 offset0 length4096 -> stageA offset4096; visible completion',
       'Response1 SUCCESS8192 -> stageA READY; consumer starts -> IN_USE',
       'Weight request2: source offset4294979584 length4096 -> stageB handle22 offset0; copy+response success',
       'Final stageA read/consumer release -> FREE; stageB consumer starts; final release -> FREE',
       'Continue all graph operations/byte requests; logits/state visible; EVALUATE17 success committed264',
       'RESET_CONTEXT18 epoch3 count264; all engines drained, state cleared; atomic all-owner rebind to epoch4/count0',
       'EVALUATE19 epoch4 reuses handles; request3 begins stageA fill across two HOST_DMA segments',
       'COPY already in flight; CANCEL control1 target19 epoch4; no further requests/copies issue',
       'Issued copy drains; service response3 CANCELED0; context invalid; one numerical CANCELED completion',
       'RESET_CONTEXT20 epoch4 count0; successful clear/rebind epoch5; EVALUATE21 epoch5 permitted',
       'Alternate fault branch: copy response permanently absent -> five-second drain expiry -> OFFLINE/quarantine; no reset/reuse until positive isolation'
    ]
    return {'scope':'contract byte fixture and required lifecycle trace, not executed RTL/transport evidence',
            'preconditions':{'native_model_and_layout_handles':[h(6),h(7)],'state_table_handle':h(5),
                'workspace_table_handle':h(8),'registered_context':7,'epoch':3,'committed':0,'capacity':4096,
                'registration_requirement':'actual complete manifests and initialized state must already pass registration; omitted model/state payload bytes are not zero substitutes',
                'all_tables_sealed':True},
            'command_hex':cmd.hex(),'tables_hex':{str(k):v.hex() for k,v in tables.items()},
            'payloads':{'token_handle':h(10),'token_ids':tokens,'modality_handle':h(12),'modality_types':modalities,
                'pixel_handle':h(11),'pixel_shape':[8,3,256,256],'pixel_bytes':pixels*2,
                'pixel_recipe':'BF16_RNE(2*((67*c+17*y+31*x+29*f+81003) mod256)/255-1); direct normalized-raster test, no tokenizer/processor equivalence claim',
                'output_handle':h(13),'output_bytes':248320*4},
            'counts':{'run_count':4,'pixel_item_count':1,'raw_patches':1024,'decoder_positions':264},
            'regions_requirement':'each table extent exactly its table length; payload extents as listed; distinct disjoint backing; table/input core READ sealed, output WRITE owner7/epoch3',
            'lifecycle':events}
