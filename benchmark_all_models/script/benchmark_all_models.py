#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SUPPORTED_EXTENSIONS = (".xml", ".onnx", ".pb", ".pdmodel", ".tflite", ".blob")
LATENCY_PATTERNS = (
    re.compile(r"Average(?: latency)?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*ms", re.IGNORECASE),
    re.compile(r"Latency\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*ms", re.IGNORECASE),
    re.compile(r"Median\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*ms", re.IGNORECASE),
)


@dataclass(frozen=True)
class InputShape:
    name: str
    dims: tuple[int, ...]


@dataclass(frozen=True)
class ShapeResolution:
    display: str
    cli_arg: str | None


@dataclass(frozen=True)
class BenchmarkResult:
    latency: str
    return_code: int
    output: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark every model under a folder with reference and target benchmark_app binaries "
            "and print a markdown comparison table."
        )
    )
    parser.add_argument("--reference-benchmark-app", required=True, type=Path)
    parser.add_argument("--target-benchmark-app", required=True, type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--device", default="CPU")
    parser.add_argument("--niter", type=int)
    parser.add_argument("--time", type=int)
    parser.add_argument("--timeout", type=int, default=0, help="Per benchmark timeout in seconds. 0 disables timeouts.")
    parser.add_argument("--output", type=Path, help="Optional path to write the markdown table.")
    parser.add_argument("--log-dir", type=Path, help="Optional directory to store per-model benchmark logs.")
    return parser.parse_args()


def discover_models(model_root: Path) -> list[Path]:
    if model_root.is_file():
        return [model_root] if model_root.suffix.lower() in SUPPORTED_EXTENSIONS else []

    models: list[Path] = []
    for path in sorted(model_root.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            models.append(path)
    return models


def display_model_name(model_root: Path, model_path: Path) -> str:
    if model_root.is_file():
        return model_path.stem
    return str(model_path.relative_to(model_root).with_suffix(""))


def parse_ir_inputs(model_path: Path) -> list[InputShape]:
    tree = ET.parse(model_path)
    root = tree.getroot()
    result: list[InputShape] = []

    for layer in root.findall("./layers/layer"):
        if layer.attrib.get("type") != "Parameter":
            continue

        input_name = layer.attrib.get("name", "input")
        output_port = layer.find("./output/port")
        if output_port is not None:
            port_names = output_port.attrib.get("names", "").split(",")
            if port_names and port_names[0].strip():
                input_name = port_names[0].strip()

        dims = tuple(resolve_input_dims(extract_raw_dims(layer), input_name))
        result.append(InputShape(name=input_name, dims=dims))

    return result


def extract_raw_dims(layer: ET.Element) -> list[str]:
    data = layer.find("./data")
    if data is not None:
        raw_shape = data.attrib.get("shape", "").strip()
        if raw_shape:
            return [item.strip() for item in raw_shape.split(",")]

    output_port = layer.find("./output/port")
    if output_port is None:
        return []

    dims: list[str] = []
    for dim in output_port.findall("./dim"):
        dims.append((dim.text or "").strip())
    return dims


def resolve_input_dims(raw_dims: list[str], input_name: str) -> list[int]:
    rank = len(raw_dims)
    return [resolve_dim(raw_dim, index, rank, input_name) for index, raw_dim in enumerate(raw_dims)]


def resolve_dim(raw_dim: str, index: int, rank: int, input_name: str) -> int:
    token = raw_dim.strip()
    if token:
        if re.fullmatch(r"[1-9][0-9]*", token):
            return int(token)

        interval_match = re.fullmatch(r"([0-9]+)?\.\.([0-9]+)?", token)
        if interval_match:
            lower_bound = interval_match.group(1)
            if lower_bound and int(lower_bound) > 0:
                return int(lower_bound)

    return fallback_dim(index=index, rank=rank, input_name=input_name)


def fallback_dim(index: int, rank: int, input_name: str) -> int:
    lower_name = input_name.lower()
    token_like = any(keyword in lower_name for keyword in ("token", "mask", "ids", "segment", "position"))
    image_like = any(keyword in lower_name for keyword in ("image", "pixel", "data", "input"))
    audio_like = any(keyword in lower_name for keyword in ("audio", "wave", "speech", "mel"))

    if token_like:
        if rank == 1:
            return 128
        if rank >= 2:
            return 1 if index == 0 else 128

    if audio_like:
        audio_defaults = {
            1: (16000,),
            2: (1, 16000),
            3: (1, 80, 300),
        }
        defaults = audio_defaults.get(rank)
        if defaults is not None and index < len(defaults):
            return defaults[index]

    if rank == 4 or image_like:
        image_defaults = (1, 3, 224, 224)
        if index < len(image_defaults):
            return image_defaults[index]

    generic_defaults = {
        1: (1,),
        2: (1, 128),
        3: (1, 128, 64),
        5: (1, 3, 16, 224, 224),
    }
    defaults = generic_defaults.get(rank)
    if defaults is not None and index < len(defaults):
        return defaults[index]

    return 1 if index == 0 else 64


def resolve_shape(model_path: Path) -> ShapeResolution:
    if model_path.suffix.lower() != ".xml":
        return ShapeResolution(display="auto", cli_arg=None)

    inputs = parse_ir_inputs(model_path)
    if not inputs:
        return ShapeResolution(display="auto", cli_arg=None)

    segments = [format_input_shape(item) for item in inputs]
    shape_arg = ",".join(segments)
    return ShapeResolution(display=shape_arg, cli_arg=shape_arg)


def format_input_shape(input_shape: InputShape) -> str:
    dims = ",".join(str(dim) for dim in input_shape.dims)
    return f"{input_shape.name}[{dims}]"


def run_benchmark(
    benchmark_app: Path,
    model_path: Path,
    device: str,
    shape: ShapeResolution,
    niter: int | None,
    time_limit: int | None,
    timeout: int,
) -> BenchmarkResult:
    command = [str(benchmark_app), "-m", str(model_path), "-d", device, "-hint", "latency"]
    if shape.cli_arg:
        command.extend(["-shape", shape.cli_arg])
    if niter is not None:
        command.extend(["-niter", str(niter)])
    if time_limit is not None:
        command.extend(["-t", str(time_limit)])

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout if timeout > 0 else None,
        )
    except subprocess.TimeoutExpired as exc:
        output = merge_streams(exc.stdout, exc.stderr)
        return BenchmarkResult(latency="TIMEOUT", return_code=124, output=output)

    output = merge_streams(completed.stdout, completed.stderr)
    latency = parse_latency(output) if completed.returncode == 0 else "ERROR"
    return BenchmarkResult(latency=latency, return_code=completed.returncode, output=output)


def merge_streams(stdout: str | bytes | None, stderr: str | bytes | None) -> str:
    merged: list[str] = []
    for stream in (stdout, stderr):
        if stream is None:
            continue
        if isinstance(stream, bytes):
            merged.append(stream.decode("utf-8", errors="replace"))
        else:
            merged.append(stream)
    return "\n".join(part for part in merged if part)


def parse_latency(output: str) -> str:
    for pattern in LATENCY_PATTERNS:
        match = pattern.search(output)
        if match:
            return f"{match.group(1)} ms"
    return "N/A"


def write_log(log_dir: Path | None, model_name: str, side: str, result: BenchmarkResult) -> None:
    if log_dir is None:
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", model_name)
    log_path = log_dir / f"{safe_name}.{side}.log"
    log_path.write_text(result.output, encoding="utf-8")


def markdown_escape(value: str) -> str:
    return value.replace("|", "\\|")


def render_table(rows: Iterable[tuple[str, str, str, str]]) -> str:
    lines = [
        "| model name | input shape | reference latency | target latency |",
        "| --- | --- | --- | --- |",
    ]
    for model_name, input_shape, reference_latency, target_latency in rows:
        lines.append(
            "| {model_name} | {input_shape} | {reference_latency} | {target_latency} |".format(
                model_name=markdown_escape(model_name),
                input_shape=markdown_escape(input_shape),
                reference_latency=markdown_escape(reference_latency),
                target_latency=markdown_escape(target_latency),
            )
        )
    return "\n".join(lines)


def validate_args(args: argparse.Namespace) -> None:
    for path in (args.reference_benchmark_app, args.target_benchmark_app):
        if not path.is_file():
            raise SystemExit(f"benchmark_app not found: {path}")
    if not args.model_dir.exists():
        raise SystemExit(f"model path not found: {args.model_dir}")


def main() -> int:
    args = parse_args()
    validate_args(args)

    models = discover_models(args.model_dir)
    if not models:
        raise SystemExit("No benchmarkable model files were found.")

    rows: list[tuple[str, str, str, str]] = []
    print(f"Discovered {len(models)} model files under {args.model_dir}", file=sys.stderr)

    for index, model_path in enumerate(models, start=1):
        model_name = display_model_name(args.model_dir, model_path)
        shape = resolve_shape(model_path)
        print(f"[{index}/{len(models)}] Benchmarking {model_name}", file=sys.stderr)

        reference = run_benchmark(
            benchmark_app=args.reference_benchmark_app,
            model_path=model_path,
            device=args.device,
            shape=shape,
            niter=args.niter,
            time_limit=args.time,
            timeout=args.timeout,
        )
        write_log(args.log_dir, model_name, "reference", reference)

        target = run_benchmark(
            benchmark_app=args.target_benchmark_app,
            model_path=model_path,
            device=args.device,
            shape=shape,
            niter=args.niter,
            time_limit=args.time,
            timeout=args.timeout,
        )
        write_log(args.log_dir, model_name, "target", target)

        rows.append((model_name, shape.display, reference.latency, target.latency))

    table = render_table(rows)
    print(table)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(table + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
