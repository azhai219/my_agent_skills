---
name: write_cpu_test
description: "Use when you need to write a new OpenVINO Intel CPU test from model details, target oneDNN kernel, ISA constraints, and expected plugin primitive selection."
---

# Write OpenVINO CPU Test (Template)
Use this skill to generate a new Intel CPU functional test from a concrete request.

## Required Input Template
Provide all fields below before writing code:

```text
Test target file:
- <absolute or workspace-relative path>

Cutoff model / graph signature:
- model path: <.../model.xml>
- key op type: <Convolution/MatMul/...>
- input shape(s): <e.g. 1x16x112x112>
- op attributes: <kernel/stride/pads/dilation/groups/...>
- output shape(s): <...>

Kernel coverage target:
- oneDNN source file: <.../jit_*.cpp>
- expected CPU primitive tag: <e.g. jit_avx2_1x1>
- expected data path: <fp32/bf16/int8/...>

ISA/runtime constraints:
- required ISA: <avx2/avx512/amx/...>
- skip policy: <e.g. skip when ISA > avx2>

Validation scope:
- should compare numerical refs: <yes/no>
- should verify primitive string in runtime model: <yes/no>
- extra env/config: <optional>
```

## Implementation Rules
1. Reuse existing test framework types in the target area (e.g. `ConvolutionLayerCPUTest`, `CPUSpecificParams`, quantization helpers).
2. Add minimal helpers for model-specific shapes/params in class-level files when needed.
3. Instantiate tests in the matching `instances/x64` or quantized instance file unless the request explicitly requires a different location.
4. If kernel target is INT8 oneDNN JIT path, add quantization info to drive int8 execution.
5. ISA gating:
- Required ISA missing: filter out params or skip.
- If request says `skip when arch > avx2`, explicitly skip on AVX512-capable hosts.
6. Keep changes surgical; avoid broad refactors.

## Suggested Workflow
1. Parse model XML and extract exact op parameters.
2. Find existing nearest test patterns (same op + precision + layout).
3. Define dedicated input shape/conv-param helper only if existing generic helpers do not match.
4. Add/choose `CPUSpecificParams` that maps to the intended primitive.
5. Add test instantiation with fusing/quantization config aligned to the model.
6. Add ISA filter/skip policy from the request.
7. Run error/lint checks for touched files.

## Output Checklist
- New test compiles in touched files.
- Graph attributes match cutoff model.
- Primitive expectation is constrained to requested kernel family.
- ISA skip behavior matches requirement.
- Summary includes touched files and exact test suite name.

## Fill-in Prompt (copy/paste)
```text
Write an OpenVINO CPU test with these details:
- test target file: <...>
- cutoff model: <...>
- kernel file to cover: <...>
- expected primitive: <...>
- required ISA and skip rule: <...>
- extra notes: <...>
```
