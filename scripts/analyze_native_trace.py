"""Read-only analysis of owned Windows CI traces. Never bundled in WrapLab."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def number(value):
    if value is None:
        return None
    value = str(value).strip()
    try:
        return int(value, 16 if value.lower().startswith("0x") else 10)
    except ValueError:
        return None


def resolve_full_trace(xml, cases):
    """Use the whole trace for object lifetimes, not only app-filtered records."""
    ns = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}
    file_objects, file_keys, registry_keys, threads = {}, {}, {}, {}
    writes, registry = Counter(), []
    network_owners, excluded_file_owners = Counter(), Counter()
    ordered = []
    for _, event in ET.iterparse(xml, events=["end"]):
        if event.tag.rsplit("}", 1)[-1] != "Event":
            continue
        system = event.find("e:System", ns)
        if system is not None:
            provider = system.find("e:Provider", ns)
            execution = system.find("e:Execution", ns)
            event_id = system.find("e:EventID", ns)
            created = system.find("e:TimeCreated", ns)
            name = provider.get("Name", "") if provider is not None else ""
            ident = number(event_id.text) if event_id is not None else None
            pid = number(execution.get("ProcessID")) if execution is not None else None
            data = {d.get("Name", ""): d.text for d in event.findall("e:EventData/e:Data", ns)}
            if (name.endswith("Kernel-Network") or
                name.endswith("Kernel-Process") and ident in {3, 4} or
                name.endswith("Kernel-File") and ident in {10, 11, 12, 13, 14, 16, 30} or
                name.endswith("Kernel-Registry") and ident in {1, 2, 3, 5, 6, 11, 13, 15}):
                ordered.append((created.get("SystemTime", "") if created is not None else "", name, ident, pid, data))
        event.clear()
    ordered.sort(key=lambda row: row[0])
    for timestamp, name, ident, pid, data in ordered:
        if name.endswith("Kernel-Process"):
            if ident == 3:
                threads[number(data.get("ThreadID"))] = number(data.get("ProcessID"))
            elif ident == 4:
                threads.pop(number(data.get("ThreadID")), None)
        elif name.endswith("Kernel-Network"):
            owner = number(data.get("PID"))
            network_owners[owner] += 1
        elif name.endswith("Kernel-File"):
            obj, key = data.get("FileObject"), data.get("FileKey")
            path = data.get("FileName") or data.get("OpenPath")
            if ident in {12, 30} and obj:
                file_objects[obj] = path  # None retires a stale reused address too.
            if ident == 10 and key:
                file_keys[key] = path
            owner = threads.get(number(data.get("IssuingThreadId")), pid)
            if ident == 16:
                if str(owner) in cases:
                    resolved = file_objects.get(obj) or file_keys.get(key)
                    writes[(cases[str(owner)], resolved)] += 1
                elif str(pid) in cases:
                    excluded_file_owners[owner] += 1
            if ident in {13, 14}:
                file_objects.pop(obj, None)
            if ident == 11:
                file_keys.pop(key, None)
        elif name.endswith("Kernel-Registry"):
            obj = data.get("KeyObject")
            relative = data.get("RelativeName")
            if ident in {1, 2} and obj and obj != "0x0" and number(data.get("Status")) == 0:
                base = data.get("BaseName") or registry_keys.get(data.get("BaseObject"))
                path = relative if relative and relative.startswith("\\") else ((base + "\\" + relative) if base and relative else base)
                registry_keys[obj] = path
            if ident in {1, 3, 5, 6, 11, 15} and str(pid) in cases:
                registry.append({"case": cases[str(pid)], "event_id": ident,
                                 "resolved_key": data.get("KeyName") or registry_keys.get(obj), "data": data})
            if ident == 13:
                registry_keys.pop(obj, None)
    return {
        "network_events_owned_by_apps": sum(n for pid, n in network_owners.items() if str(pid) in cases),
        "all_trace_network_owner_counts": {str(k): v for k, v in network_owners.items()},
        "registry_create_or_mutation_with_resolved_keys": registry,
        "file_write_counts_with_lifetime_mapping": [{"case": c, "path": p, "count": n} for (c, p), n in writes.items()],
        "file_write_events_with_unresolved_paths": sum(n for (c, p), n in writes.items() if p is None),
        "execution_context_file_writes_excluded_by_other_issuing_thread_owner": dict(excluded_file_owners),
        "limitations": ["ETW buffers are sorted by timestamp before full-trace object lifetime resolution; handles retire at cleanup/close.",
                        "File ownership prefers known issuing-thread PID; otherwise uses execution PID. Unknown names remain unknown.",
                        "No stack capture; a registry event's PID alone does not identify the user-mode caller or kernel subsystem."],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("events", type=Path)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--xml", type=Path)
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
        row["case_by_data_pid"] = {k: cases.get(str(number(v))) for k, v in data.items() if k.lower() in {"pid", "processid", "clientprocessid"}}
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
    if args.xml:
        report["full_trace_resolution"] = resolve_full_trace(args.xml, cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"network_events": len(network), "wmi_events": len(wmi), "registry_create_or_mutation_events": len(registry), "file_mutation_events": len(writes)}))


if __name__ == "__main__":
    main()
