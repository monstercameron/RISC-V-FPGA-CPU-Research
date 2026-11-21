"""Synthetic FP32 schedule checks, not checkpoint validation or RTL testing.
Independent whole-matrix versus column-panel Delta updates, with resumable chunks;
six-head GQA shared reads versus separate head reads, including BF16 probability cast.
"""
import json
from pathlib import Path
import numpy as np

rng=np.random.default_rng(3812702)
dk,dv,tokens=128,128,9
q=rng.normal(size=(tokens,dk)).astype(np.float32)/np.sqrt(dk)
k=rng.normal(size=(tokens,dk)).astype(np.float32)
k/=np.sqrt(np.sum(k*k,axis=-1,keepdims=True)+1e-6)
v=rng.normal(size=(tokens,dv)).astype(np.float32)
d=rng.uniform(.7,1,tokens).astype(np.float32)
b=rng.uniform(.1,.9,tokens).astype(np.float32)
initial=rng.normal(0,.1,(dk,dv)).astype(np.float32)

def whole():
    s=initial.copy(); out=[]
    for t in range(tokens):
        decayed=s*d[t]
        pred=np.sum(k[t,:,None]*decayed,axis=0,dtype=np.float32)
        delta=(v[t]-pred)*b[t]
        s=decayed+k[t,:,None]*delta[None,:]
        out.append(np.sum(q[t,:,None]*s,axis=0,dtype=np.float32))
    return np.array(out),s

def panel(width,chunk):
    s=initial.copy();out=np.zeros((tokens,dv),np.float32);reads=writes=0
    for start in range(0,tokens,chunk):
        for col in range(0,dv,width):
            stop=min(col+width,dv)
            local=s[:,col:stop].copy();reads+=local.nbytes
            for t in range(start,min(tokens,start+chunk)):
                local*=d[t]
                pred=np.zeros(stop-col,np.float32)
                for key in range(dk):
                    pred+=k[t,key]*local[key]
                correction=b[t]*(v[t,col:stop]-pred)
                result=np.zeros(stop-col,np.float32)
                for key in range(dk):
                    local[key]+=k[t,key]*correction
                    result+=q[t,key]*local[key]
                out[t,col:stop]=result
            s[:,col:stop]=local;writes+=local.nbytes
    return out,s,reads,writes

yr,sr=whole();cases=[]
for width in (1,8,16,31,128):
    for chunk in (1,4,9):
        y,s,rd,wr=panel(width,chunk)
        ye=float(np.max(np.abs(yr-y)));se=float(np.max(np.abs(sr-s)))
        assert ye<2e-5 and se<2e-5,(width,chunk,ye,se)
        assert rd==wr==initial.nbytes*((tokens+chunk-1)//chunk)
        cases.append(dict(width=width,chunk=chunk,output_max_abs=ye,state_max_abs=se,read_bytes=rd,write_bytes=wr))

def bf16(x):
    a=x.astype(np.float32).view(np.uint32)
    return ((a+np.uint32(0x7fff)+((a>>16)&1))&np.uint32(0xffff0000)).view(np.float32)

S,D,G=37,256,6
queries=bf16(rng.normal(0,.2,(G,D)))
keys=bf16(rng.normal(0,.2,(S,D)));values=bf16(rng.normal(0,.2,(S,D)))
def attention(shared):
    outputs=[];key_bytes=0;value_bytes=0
    groups=[list(range(G))] if shared else [[h] for h in range(G)]
    answer=np.zeros((G,D),np.float32)
    for heads in groups:
        mx=np.full(len(heads),-np.inf,np.float32);den=np.zeros(len(heads),np.float32)
        for stage in range(3):
            for p in range(S):
                key_bytes+=D*2
                if stage==2:value_bytes+=D*2
                for i,h in enumerate(heads):
                    score=np.sum(queries[h]*keys[p],dtype=np.float32)/16
                    if stage==0:mx[i]=max(mx[i],score)
                    elif stage==1:den[i]+=np.exp(score-mx[i])
                    else:
                        prob=bf16(np.asarray(np.exp(score-mx[i])/den[i]))
                        answer[h]+=prob*values[p]
        outputs.extend(heads)
    assert sorted(outputs)==list(range(G))
    return answer,key_bytes+value_bytes

a,old=attention(False);z,new=attention(True)
assert np.array_equal(a,z) and old==6*new
result=dict(status="synthetic software scheduling probe only",seed=3812702,delta_cases=cases,
            gqa=dict(context=S,group=G,output_max_abs=float(np.max(np.abs(a-z))),
                     ungrouped_bytes=old,grouped_bytes=new,traffic_ratio=old/new))
Path(__file__).with_name("memory-schedule-probe.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(dict(delta_cases=len(cases),delta_max_abs=max(x["output_max_abs"] for x in cases),gqa=result["gqa"]),indent=2))
