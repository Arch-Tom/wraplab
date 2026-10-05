"""Read-only analysis of owned Windows CI traces. Never bundled in WrapLab."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("events", type=Path)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    events = json.loads(args.events.read_text(encoding="utf-8"))
    runtime = json.loads(args.runtime.read_text(encoding="utf-8"))
    cases = {str(c["primary_pid"]): c["mode"] + "-" + c["operation"] for c in runtime["cases"]}
    groups, examples, paths, writes = defaultdict(Counter), defaultdict(list), {}, []
    network, registry, processes, wmi = [], [], [], []
    for row in events:
        provider = row["provider"]
        groups[provider][str(row["event_id"])] += 1
        data = row["data"]
        row["case_by_execution_pid"] = cases.get(row["execution_pid"])
        row["case_by_data_pid"] = {k: cases.get(str(v)) for k, v in data.items() if k.lower() in {"pid", "processid", "clientprocessid"}}
        key = provider + ":" + str(row["event_id"])
        if len(examples[key]) < 2:
            examples[key].append(row)
        if provider.endswith("Kernel-Network"):
            network.append(row)
        elif provider.endswith("WMI-Activity"):
            wmi.append(row)
        elif provider.endswith("Kernel-Process") and str(row["event_id"]) in {"1", "2"}:
            processes.append(row)
        elif provider.endswith("Kernel-Registry") and str(row["event_id"]) in {"1", "3", "5", "6", "11", "15"}:
            registry.append(row)
        elif provider.endswith("Kernel-File"):
            name = next((v for k, v in data.items() if k in {"FileName", "OpenPath", "FilePath", "Path"}), None)
            if name:
                for k in {"FileObject", "FileKey"}:
                    if data.get(k):
                        paths[data[k]] = name
            if str(row["event_id"]) in {"16", "18", "19", "26", "27", "28", "29", "30", "34"}:
                resolved = name or paths.get(data.get("FileObject")) or paths.get(data.get("FileKey"))
                writes.append({**row, "resolved_path": resolved})
    write_counts = Counter((r["case_by_execution_pid"], r["event_id"], r["resolved_path"]) for r in writes)
    report = {
        "source_commit_of_tested_candidate": runtime["source_commit"],
        "candidate_zip": runtime["candidate_zip"],
        "cases": cases, "events_by_provider_and_id": {k: dict(v) for k, v in groups.items()},
        "network_events": network, "wmi_events": wmi,
        "registry_create_or_mutation_events": registry,
        "process_start_stop_events": processes,
        "file_write_mutation_counts": [{"case": c, "event_id": i, "resolved_path": p, "count": n} for (c, i, p), n in write_counts.items()],
        "unresolved_write_mutation_event_count": sum(r["resolved_path"] is None for r in writes),
        "provider_event_examples": dict(examples),
        "limitations": ["Counts include PID associations, not proof of application-owned activity. Inspect execution and payload PID separately.",
                        "tracerpt warned about schema mismatches. Keep raw ETL; unknown paths/payloads are not silently resolved.",
                        "Registry CreateKey can open existing keys; it is not by itself evidence of persistence.",
                        "File-name mapping is best effort from captured Create/Name events, not a complete causal filesystem graph."],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"network_events": len(network), "wmi_events": len(wmi), "registry_create_or_mutation_events": len(registry), "file_mutation_events": len(writes)}))


if __name__ == "__main__":
    main()
