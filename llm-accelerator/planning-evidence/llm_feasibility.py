"""Planning experiment only: numerical and sizing checks, not accelerator RTL."""
import json, math, platform, time
from pathlib import Path
import numpy as np

start=time.perf_counter()
rng=np.random.default_rng(23010)
H,I=128,384
wu=rng.normal(0,1/math.sqrt(H),(I,H))
wg=rng.normal(0,1/math.sqrt(H),(I,H))
wd=rng.normal(0,1/math.sqrt(I),(H,I))
cal=rng.normal(0,.5,(32,H))
test=rng.normal(0,.5,(32,H))

def silu(x): return x/(1+np.exp(-x))
def away(x): return np.sign(x)*np.floor(np.abs(x)+.5)
def exponent(maximum,limit):
    return np.ceil(np.log2(np.maximum(maximum,1e-12)/limit)).astype(np.int64)
def quant(x,e,limit): return np.clip(away(x/np.exp2(e)),-limit,limit).astype(np.int64)
def requant(a,e,limit):
    # Scalar arbitrary precision specifies ties away from zero, including negative values.
    flat=np.asarray(a).ravel(); es=np.broadcast_to(e,np.shape(a)).ravel()
    vals=[]
    for value,shift in zip(flat,es):
        v,s=int(value),int(shift)
        if s>=0: z=v<<s
        else:
            n=-s; z=((abs(v)+(1<<(n-1)))>>n)*(1 if v>=0 else -1)
        vals.append(max(-limit-1,min(limit,z)))
    return np.array(vals,dtype=np.int64).reshape(np.shape(a))

lut=away(silu(np.arange(-2048,2049)/256)*256).astype(np.int64)
def lut_silu(g):
    idx=np.clip(g,-2048,2048)+2048
    return np.where(g>2048,g,np.where(g < -2048,0,lut[idx]))

def run(x,bits):
    limit=2**(bits-1)-1
    ew=[exponent(np.max(np.abs(w),axis=1),limit) for w in (wu,wg,wd)]
    qw=[quant(w,e[:,None],limit) for w,e in zip((wu,wg,wd),ew)]
    ex=int(exponent(np.max(np.abs(cal)),127))
    # Determine intermediate activation scale from calibration only.
    fc=silu(cal@wg.T)*(cal@wu.T)
    eh=int(exponent(np.max(np.abs(fc)),127))
    xq=quant(x,ex,127)
    up=requant(xq@qw[0].T,ex+ew[0]+8,32767)
    gate=requant(xq@qw[1].T,ex+ew[1]+8,32767)
    hidden=requant(up*lut_silu(gate),-16-eh,127)
    outq=requant(hidden@qw[2].T,eh+ew[2]+8,32767)
    out=outq/256
    reference=(silu(x@wg.T)*(x@wu.T))@wd.T
    error=out-reference
    nrmse=float(np.linalg.norm(error)/np.linalg.norm(reference))
    cosine=float(np.sum(out*reference)/(np.linalg.norm(out)*np.linalg.norm(reference)))
    return dict(bits=bits,nrmse=nrmse,cosine=cosine,max_abs_error=float(np.max(np.abs(error))),
                input_exponent=ex,hidden_exponent=eh,
                output_saturated=int(np.sum((outq==-32768)|(outq==32767))),
                hidden_saturated=int(np.sum((hidden==-128)|(hidden==127))))

metrics=[run(test,b) for b in (8,4)]
grid=np.arange(-32768,32768,dtype=np.int64)
max_silu=float(np.max(np.abs(lut_silu(grid)/256-silu(grid/256))))
assert max_silu < .003
assert metrics[0]['nrmse']<.08 and metrics[0]['cosine']>.995
for m in metrics:
    m['initial_quality_gate_pass'] = bool(m['nrmse'] < (.08 if m['bits']==8 else .15)
                                        and m['cosine'] > (.995 if m['bits']==8 else .98))
assert metrics[0]['initial_quality_gate_pass']
assert all(m['output_saturated']==0 for m in metrics)
assert int(requant(np.array([-3,3]),-1,127)[0])==-2
P=8;Q=1
report=dict(seed=23010,numpy=np.__version__,python=platform.python_version(),H=H,I=I,
            calibration_vectors=32,holdout_vectors=32,synthetic_only=True,metrics=metrics,
            silu_max_absolute_error_over_all_int16_inputs=max_silu,
            demo_macs=3*H*I,demo_w4_bytes=3*H*I//2,
            qwen_ffn_macs=3*5120*17408,qwen_ffn_w4_bytes=3*5120*17408//2,
            demo_ideal_mac_cycles=3*H*I//(P*Q),
            qwen_ideal_mac_cycles=3*5120*17408//(P*Q),
            mac_bound_w4_k17408=17408*128*8,
            mac_bound_w8_k17408=17408*128*128,
            nominal_clock_mhz=100,nominal_w8_weight_bytes_per_cycle=P*Q,
            nominal_w4_weight_bytes_per_cycle=P*Q//2,
            elapsed_seconds=time.perf_counter()-start)
path=Path(__file__).with_name('llm-feasibility.json')
path.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
