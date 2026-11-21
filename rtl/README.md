# RTL

The original CPU implementation is in [cpu/rv64_core.sv](cpu/rv64_core.sv), with a synchronous RAM wrapper in [cpu/rv64_bram_soc.sv](cpu/rv64_bram_soc.sv). Read the [CPU architecture](../cpu/architecture.md) and run the custom simulation suite before changing it.

The historical third-party CPU remains in `sim/starter/vendor/` under its ISC license. The LLM accelerator RTL is future work governed by its separate implementation/ABI/adapter contracts.
