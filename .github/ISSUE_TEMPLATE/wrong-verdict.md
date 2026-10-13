---
name: Wrong verdict or bad reading
about: gpumedic flagged a healthy GPU, missed a broken one, or read a number wrong
labels: bug
---

**What gpumedic said, and what was actually true**

<!-- e.g. "DRAIN for thermal.slowdown, but nvidia-smi shows 60°C" -->

**GPU, driver and where it runs**

<!-- e.g. "H100 SXM, driver 550.54.15, bare metal" or "RTX 4090, driver 580, RunPod container" -->

**`gpumedic scan --json`**

<!-- Paste it, or attach the folder from `gpumedic capture`.
     Remove the hostname and GPU UUIDs first if they identify your machines. -->

```json

```

**`nvidia-smi` at the same moment**

```

```
