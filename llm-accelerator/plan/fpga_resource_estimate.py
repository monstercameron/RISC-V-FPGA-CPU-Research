"""Planning envelopes, NOT synthesis results. Run with Python standard library.
LUT estimates assume DSP-mapped FP32 arithmetic, shared operators and BRAM storage.
"""
import json
from pathlib import Path

SHARED = {
    "sequencer_descriptors_64bit_addressing": (3000,6000),
    "attention_delta_ffn_vision_controllers": (3000,6000),
    "vector_norm_reduction_control": (2000,5000),
    "shared_div_sqrt_conversions": (1000,3000),
    "shared_nonlinear_engine": (2000,6000),
    "tensor_dma_scratch_routing_credits": (5000,10000),
    "debug_counters": (1000,3000),
    "reset_clock_control": (1000,1000),
}
DEVICES = {
    "XC7A100T": dict(lut6=63400,ff=126800,dsp=240,bram36=135,uram288=0),
    "XC7A200T": dict(lut6=134600,ff=269200,dsp=740,bram36=365,uram288=0),
    "XC7K325T": dict(lut6=203800,ff=407600,dsp=840,bram36=445,uram288=0),
    "XCKU3P": dict(lut6=162720,ff=325440,dsp=1368,bram36=360,uram288=48),
    "XCKU5P": dict(lut6=216960,ff=433920,dsp=1824,bram36=480,uram288=64),
}

def report():
    shared=[sum(v[i] for v in SHARED.values()) for i in (0,1)]
    profiles=[]
    for lanes in (1,8,32,64):
        core=[shared[i]+lanes*(1000,2000)[i] for i in (0,1)]
        wide=[int(x*.25) for x in core] if lanes>=32 else [0,0]
        total=[core[i]+wide[i]+(8000,16000)[i]+(7000,16000)[i] for i in (0,1)]
        dsp=[(8,32)[i]+lanes*(2,4)[i]+(3,8)[i] for i in (0,1)]
        profiles.append(dict(lanes=lanes,core_lut6=core,wide_routing_allowance=wide,
                             with_one_ddr_and_one_pcie_dma_lut6=total,dsp_envelope=dsp,
                             dense_only_seconds_at_200MHz=25621954560/(lanes*200e6)))
    bram=dict(scratch_64_to_128KiB=(24,48),nonlinear_rom=(4,12),
              extra_transport_cdc=(8,20),ddr_controller=(24,32),pcie_dma=(8,40),debug=(4,16))
    bram_total=[sum(v[i] for v in bram.values()) for i in (0,1)]
    eight=next(x for x in profiles if x['lanes']==8)
    fits={name:dict(lut_use_percent=[100*x/d['lut6'] for x in eight['with_one_ddr_and_one_pcie_dma_lut6']],
                    high_fits_65percent_design_target=eight['with_one_ddr_and_one_pcie_dma_lut6'][1]<=.65*d['lut6'],
                    bram_use_percent=[100*x/d['bram36'] for x in bram_total]) for name,d in DEVICES.items()}
    result=dict(status='analytical envelope, no RTL synthesis or routing performed',
                shared_lut_assumptions=SHARED,shared_lut_total=shared,
                per_lane_lut=(1000,2000),ddr_lut=(8000,16000),pcie_dma_lut=(7000,16000),
                wide_note='Additional 25% of core LUT allowance at 32/64 lanes for fanout/routing/control growth.',
                profiles=profiles,bram36_assumptions_for_8lane=bram,bram36_total=bram_total,
                devices=DEVICES,eight_lane_fit= fits,
                pcie_encoding_upper_GBps=dict(gen3x4=8e9*4*(128/130)/8/1e9,
                    gen3x8=8e9*8*(128/130)/8/1e9,gen2x4=5e9*4*(8/10)/8/1e9),
                sources=dict(fp='https://download.amd.com/docnav/documents/ip_attachments/floating-point.html',
                    ddr='https://download.amd.com/docnav/documents/ip_attachments/ddr4.html',
                    dma='https://download.amd.com/docnav/documents/ip_attachments/xdma.html',
                    kintexplus='https://docs.amd.com/v/u/en-US/ds890-ultrascale-overview',
                    series7='https://docs.amd.com/v/u/en-US/7-series-product-selection-guide'),
                warnings=['AMD IP counts are anchors, not HardFloat measurements.',
                    'Device resource sufficiency does not establish board DDR/PCIe availability or timing.',
                    'No 27B weights are stored in LUTs; complete graph shares hardware over time.',
                    'The 65% utilization threshold is a conservative project target, not a device rule.'])
    assert shared==[18000,40000]
    assert eight['with_one_ddr_and_one_pcie_dma_lut6']==[41000,88000]
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--out',default='fpga-resource-estimate.json')
    args=p.parse_args()
    r=report()
    Path(args.out).write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:r[k] for k in ('profiles','bram36_total','eight_lane_fit')},indent=2))
