#!/usr/bin/env python3

import argparse
import csv
import importlib.util
from pathlib import Path
import re

import numpy as np


def load_ieb_reader(dump_check_path: Path):
    spec = importlib.util.spec_from_file_location("dump_check", dump_check_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.IEB


def collect_ieb_files(folder: Path):
    items = {}
    for file_path in sorted(folder.iterdir()):
        if not file_path.name.endswith(".ieb"):
            continue
        split = file_path.name.find("_")
        if split < 0 or not file_path.name.startswith("#"):
            continue
        exec_id = int(file_path.name[1:split])
        logical_name = file_path.name[split + 1:]
        items[logical_name] = {
            "exec_id": exec_id,
            "path": file_path,
        }
    return items


def parse_blob_name(logical_name: str):
    stem = logical_name[:-4] if logical_name.endswith(".ieb") else logical_name
    port_match = re.search(r"_(in|out)(\d+)$", stem)
    if port_match:
        port_kind = port_match.group(1).upper()
        port_index = port_match.group(2)
        base = stem[: port_match.start()]
    else:
        internal_match = re.search(r"_blb(\d+)$", stem)
        if internal_match:
            port_kind = "INTERNAL"
            port_index = internal_match.group(1)
            base = stem[: internal_match.start()]
        else:
            port_kind = "UNKNOWN"
            port_index = ""
            base = stem

    first_sep = base.find("_")
    if first_sep >= 0:
        op_type = base[:first_sep]
        node_name = base[first_sep + 1 :]
    else:
        op_type = ""
        node_name = base

    return op_type, node_name, port_kind, port_index


def build_rows(ref_items, target_items, ieb_reader):
    all_names = sorted(set(ref_items) | set(target_items))
    rows = []

    for logical_name in all_names:
        ref_item = ref_items.get(logical_name)
        target_item = target_items.get(logical_name)
        op_type, node_name, port_kind, port_index = parse_blob_name(logical_name)

        if not ref_item or not target_item:
            rows.append(
                {
                    "status": "missing",
                    "op_type": op_type,
                    "node_name": node_name,
                    "kind": port_kind,
                    "port": port_index,
                    "logical_name": logical_name,
                    "ref_exec_id": "" if not ref_item else ref_item["exec_id"],
                    "target_exec_id": "" if not target_item else target_item["exec_id"],
                    "shape": "",
                    "dtype": "",
                    "max_abs": "",
                    "mean_abs": "",
                    "std_abs": "",
                }
            )
            continue

        ref_ieb = ieb_reader(str(ref_item["path"]))
        target_ieb = ieb_reader(str(target_item["path"]))

        ref_value = ref_ieb.value.astype(np.float32, copy=False)
        target_value = target_ieb.value.astype(np.float32, copy=False)

        if ref_value.shape != target_value.shape:
            status = "shape_mismatch"
            shape = f"{tuple(ref_value.shape)} vs {tuple(target_value.shape)}"
            max_abs = ""
            mean_abs = ""
            std_abs = ""
        else:
            diff = np.abs(ref_value - target_value)
            status = "same" if np.all(diff == 0) else "diff"
            shape = str(tuple(ref_value.shape))
            max_abs = float(np.max(diff))
            mean_abs = float(np.mean(diff))
            std_abs = float(np.std(diff))

        rows.append(
            {
                "status": status,
                "op_type": op_type,
                "node_name": node_name,
                "kind": port_kind,
                "port": port_index,
                "logical_name": logical_name,
                "ref_exec_id": ref_item["exec_id"],
                "target_exec_id": target_item["exec_id"],
                "shape": shape,
                "dtype": str(ref_ieb.value.dtype),
                "max_abs": max_abs,
                "mean_abs": mean_abs,
                "std_abs": std_abs,
            }
        )

    rows.sort(key=sort_rows)
    return rows


def sort_rows(row):
    exec_id = row["ref_exec_id"] if row["ref_exec_id"] != "" else 10**9
    status_rank = {"diff": 0, "shape_mismatch": 1, "missing": 2, "same": 3}.get(row["status"], 9)
    return (exec_id, status_rank, row["logical_name"])


def write_csv(rows, output_path: Path):
    fieldnames = [
        "status",
        "op_type",
        "node_name",
        "kind",
        "port",
        "logical_name",
        "ref_exec_id",
        "target_exec_id",
        "shape",
        "dtype",
        "max_abs",
        "mean_abs",
        "std_abs",
    ]
    with output_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows, output_path: Path):
    with output_path.open("w") as file:
        file.write(
            "| status | ref_exec_id | target_exec_id | kind | port | op_type | node_name | max_abs | mean_abs | std_abs | logical_name |\n"
        )
        file.write(
            "|---|---:|---:|---|---:|---|---|---:|---:|---:|---|\n"
        )
        for row in rows:
            file.write(
                "| {status} | {ref_exec_id} | {target_exec_id} | {kind} | {port} | {op_type} | {node_name} | {max_abs} | {mean_abs} | {std_abs} | {logical_name} |\n".format(
                    **row
                )
            )


def write_first_bad(rows, output_path: Path):
    first_bad = next((row for row in rows if row["status"] != "same"), None)
    with output_path.open("w") as file:
        if first_bad is None:
            file.write("All matched blobs are identical.\n")
            return None
        for key in [
            "status",
            "ref_exec_id",
            "target_exec_id",
            "kind",
            "port",
            "op_type",
            "node_name",
            "logical_name",
            "shape",
            "dtype",
            "max_abs",
            "mean_abs",
            "std_abs",
        ]:
            file.write(f"{key}: {first_bad[key]}\n")
        return first_bad


def main():
    parser = argparse.ArgumentParser(description="Summarize OpenVINO CPU blob diff results.")
    parser.add_argument("--ref-dir", required=True)
    parser.add_argument("--target-dir", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--dump-check", required=True)
    args = parser.parse_args()

    ref_dir = Path(args.ref_dir)
    target_dir = Path(args.target_dir)
    output_root = Path(args.output_root)
    dump_check = Path(args.dump_check)

    ieb_reader = load_ieb_reader(dump_check)
    ref_items = collect_ieb_files(ref_dir)
    target_items = collect_ieb_files(target_dir)
    rows = build_rows(ref_items, target_items, ieb_reader)

    write_csv(rows, output_root / "blob_diff.csv")
    write_markdown(rows, output_root / "blob_diff.md")
    first_bad = write_first_bad(rows, output_root / "first_bad_blob.txt")

    if first_bad is None:
        print("All matched blobs are identical.")
    else:
        print("First different blob:")
        print(
            "  exec_id(ref/target)={}/{} kind={} op_type={} node_name={} max_abs={}".format(
                first_bad["ref_exec_id"],
                first_bad["target_exec_id"],
                first_bad["kind"],
                first_bad["op_type"],
                first_bad["node_name"],
                first_bad["max_abs"],
            )
        )


if __name__ == "__main__":
    main()