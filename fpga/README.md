# FPGA integration

Place target-specific constraints, build scripts and documented board adapters here when implemented. Pin the exact PCB, FPGA part, clock/reset/DDR/PCIe configuration and vendor-tool version. Generated bitstreams and tool build trees belong in ignored build directories.

The current candidate boards and host prerequisites are documented in the root FPGA resource analysis. No complete target build or deployment is claimed.

The current first hardware target is the [custom CPU and RAM wrapper](../cpu/README.md). Its core is simulation-tested. Exact-part synthesis, BRAM inference, board clock/reset and pin constraints still need implementation and validation.
