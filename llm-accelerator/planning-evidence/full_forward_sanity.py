"""Planning-only float graph probe: causal full sequence vs cached text decode.
Not RTL, not a checkpoint benchmark, not a numeric-precision certification.
"""
from pathlib import Path
import json, math, hashlib
import numpy as np

rng=np.random.default_rng(38127)
H,I,V,L,T=32,64,64,4,8
Q,KV,D=6,1,8
KH,VH,DK,DV=1,3,4,4
def mat(o,i): return rng.normal(0,.07,(o,i)).astype(np.float32)
def rms(x,w): return (x/np.sqrt(np.mean(x*x,axis=-1,keepdims=True)+1e-6))*(1+w)
def l2(x): return x/np.sqrt(np.sum(x*x,axis=-1,keepdims=True)+1e-6)
def silu(x): return x/(1+np.exp(-x))
def sigmoid(x): return 1/(1+np.exp(-x))
embedding=mat(V,H); head=mat(V,H)
layers=[]
for l in range(L):
    layer=dict(n1=np.zeros(H,np.float32),n2=np.zeros(H,np.float32),up=mat(I,H),gate=mat(I,H),down=mat(H,I))
    if l%4==3:
        layer.update(q=mat(2*Q*D,H),k=mat(KV*D,H),v=mat(KV*D,H),out=mat(H,Q*D))
    else:
        C=2*KH*DK+VH*DV
        layer.update(qkv=mat(C,H),z=mat(VH*DV,H),a=mat(VH,H),b=mat(VH,H),out=mat(H,VH*DV),
                     conv=rng.normal(0,.2,(C,4)).astype(np.float32),A=np.full(VH,.3,np.float32),
                     bias=np.zeros(VH,np.float32),gamma=np.ones(DV,np.float32))
    layers.append(layer)

def initial():
    return [dict(S=np.zeros((VH,DK,DV),np.float32),hist=np.zeros((2*KH*DK+VH*DV,4),np.float32))
            if i%4!=3 else dict(K=[],V=[]) for i in range(L)]
def rope(x,pos):
    # Tiny partial RoPE has two rotary coordinates: rotate_half halves of that subvector.
    out=x.copy(); c,s=math.cos(pos),math.sin(pos)
    out[...,0]=x[...,0]*c-x[...,1]*s
    out[...,1]=x[...,1]*c+x[...,0]*s
    return out
def block(x,layer,state,pos):
    n=rms(x,layer['n1'])
    if 'qkv' in layer:
        mixed=layer['qkv']@n
        state['hist'][:,:-1]=state['hist'][:,1:]
        state['hist'][:,-1]=mixed
        conv=silu(np.sum(state['hist']*layer['conv'],axis=-1))
        q,k,v=np.split(conv,[KH*DK,2*KH*DK])
        q=np.repeat(l2(q.reshape(KH,DK)),VH//KH,axis=0)/math.sqrt(DK)
        k=np.repeat(l2(k.reshape(KH,DK)),VH//KH,axis=0)
        v=v.reshape(VH,DV)
        beta=sigmoid(layer['b']@n)
        decay=np.exp(-layer['A']*np.logaddexp(0,layer['a']@n+layer['bias']))
        S=state['S']*decay[:,None,None]
        prediction=np.einsum('hk,hkv->hv',k,S)
        delta=(v-prediction)*beta[:,None]
        S+=k[:,:,None]*delta[:,None,:]
        y=np.einsum('hk,hkv->hv',q,S)
        state['S']=S
        y=y/np.sqrt(np.mean(y*y,axis=-1,keepdims=True)+1e-6)
        y=y*layer['gamma']*silu((layer['z']@n).reshape(VH,DV))
        mixed_out=layer['out']@y.reshape(-1)
    else:
        qgate=(layer['q']@n).reshape(Q,2*D)
        q,gate=np.split(qgate,2,axis=-1)
        q=rope(rms(q,np.zeros(D,np.float32)),pos)
        k=rope(rms((layer['k']@n).reshape(KV,D),np.zeros(D,np.float32)),pos)
        v=(layer['v']@n).reshape(KV,D)
        state['K'].append(k);state['V'].append(v)
        keys=np.stack(state['K']); values=np.stack(state['V'])
        y=[]
        for h in range(Q):
            group=h//(Q//KV)
            score=keys[:,group]@q[h]/math.sqrt(D)
            probs=np.exp(score-np.max(score));probs/=np.sum(probs)
            y.append(probs@values[:,group])
        y=np.array(y)*sigmoid(gate)
        mixed_out=layer['out']@y.reshape(-1)
    residual=x+mixed_out
    n=rms(residual,layer['n2'])
    return residual+layer['down']@(silu(layer['gate']@n)*(layer['up']@n))

def token_major(tokens,state=None,offset=0):
    state=initial() if state is None else state
    logits=[]
    for p,t in enumerate(tokens,offset):
        x=embedding[t].copy()
        for layer,s in zip(layers,state): x=block(x,layer,s,p)
        logits.append(head@rms(x,np.zeros(H,np.float32)))
    return np.array(logits),state

def layer_major(tokens):
    state=initial(); xs=embedding[tokens].copy()
    for layer,s in zip(layers,state):
        xs=np.array([block(x,layer,s,p) for p,x in enumerate(xs)])
    return np.array([head@rms(x,np.zeros(H,np.float32)) for x in xs]),state

tokens=rng.integers(0,V,T)
a,sa=token_major(tokens); b,sb=layer_major(tokens)
prefix,sp=token_major(tokens[:3]); suffix,sp=token_major(tokens[3:],sp,3)
changed=tokens.copy();changed[-1]=(changed[-1]+1)%V
c,_=token_major(changed)
reset,_=token_major(tokens)
errors=dict(schedule=float(np.max(np.abs(a-b))),resume=float(np.max(np.abs(a-np.concatenate([prefix,suffix])))),
            causality=float(np.max(np.abs(a[:-1]-c[:-1]))),reset=float(np.max(np.abs(a-reset))),
            final_state=float(max(np.max(np.abs(x['S']-y['S'])) for x,y in zip(sa,sb) if 'S'in x)))
assert max(errors.values())<1e-5
assert np.isfinite(a).all()
report=dict(seed=38127,profile=dict(H=H,I=I,V=V,layers=L,tokens=T,delta_layers=3,full_attention_layers=1,
                                  query_heads=Q,kv_heads=KV,head_dim=D,query_width=Q*D,
                                  delta_qk_heads=KH,delta_value_heads=VH),
            checks=errors,finite_logits=bool(np.isfinite(a).all()),shape=list(a.shape),
            warning='Tiny synthetic NumPy text graph only; shared block implementation, no RTL or pretrained accuracy proof.')
Path(__file__).with_name('full-forward-sanity.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
