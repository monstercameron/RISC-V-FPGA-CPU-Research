"""Fetch only safetensors JSON headers, refusing non-range responses."""
import concurrent.futures,json,struct,urllib.request
from pathlib import Path
base=Path(__file__).parent
index=json.loads((base/'qwen-weight-index.json').read_text())
out=base/'qwen-headers';out.mkdir(exist_ok=True)
def get_range(url,start,end):
    req=urllib.request.Request(url,headers={'Range':f'bytes={start}-{end}','User-Agent':'LLM-dimension-planning/1.0'})
    with urllib.request.urlopen(req,timeout=40) as r:
        if r.status!=206 or not r.headers.get('Content-Range','').startswith(f'bytes {start}-'):
            raise RuntimeError('Server did not honor bounded Range request; stopped before reading body')
        data=r.read(end-start+2)
        if len(data)!=end-start+1: raise RuntimeError('Unexpected range length')
        return data
def fetch(shard):
    target=out/(shard+'.json')
    if target.exists(): return shard,len(target.read_bytes())
    url='https://huggingface.co/Qwen/Qwen3.8-27B/resolve/main/'+shard
    n=struct.unpack('<Q',get_range(url+'?header_size=1',0,7))[0]
    if not (0<n<8_000_000): raise RuntimeError('Implausible header size')
    data=get_range(url+'?header_json=1',8,7+n)
    value=json.loads(data)
    target.write_text(json.dumps(value,indent=2)+'\n')
    return shard,n
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    for result in pool.map(fetch,sorted(set(index['weight_map'].values()))):print(result,flush=True)
