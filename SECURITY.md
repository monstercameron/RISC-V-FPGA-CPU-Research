# Security reporting

This repository contains experimental research and development material. There is no production-supported release or promised security response SLA.

For a suspected vulnerability that could expose host memory, credentials or another person's data, use the repository's **Security → Report a vulnerability** option when private reporting is enabled. If no private route is configured, open a minimal issue requesting a private contact method without exploit details or sensitive data. No private reporting address is currently designated in this repository.

Include the affected revision, component, platform/tool versions, impact and a minimal reproduction through the private channel. Exclude credentials, private model/input data and unnecessary memory dumps. Ordinary numerical errors and research questions can use public issue forms.

Descriptor bounds, DMA ownership, stale IDs, canceled transfers, reset and fatal isolation are required design gates in the implementation/ABI/adapter contracts. A passing planning check does not establish that a future driver or bitstream safely implements them.
