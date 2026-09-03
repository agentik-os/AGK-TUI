#!/usr/bin/env python3
"""Deterministic contract operations for media-os."""
from pathlib import Path
import argparse, hashlib, json, re
OS_ID = 'media-os'

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("action", choices=["contract", "handoff-check"])
    parser.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parents[1])
    args=parser.parse_args(); root=args.package_root.resolve()
    if args.action == "contract":
        path=root/"CONTRACT.json"; data=path.read_bytes()
        print(json.dumps({"os_id":OS_ID,"path":str(path),"sha256":hashlib.sha256(data).hexdigest()},sort_keys=True)); return 0
    text=(root/"research/14_BUILDER_HANDOFF.md").read_text(encoding="utf-8")
    ids=re.findall(r"^### INPUT-(\d{2})\b",text,re.M)
    result={"os_id":OS_ID,"input_count":len(ids),"folded":"FOLDED_BY_BUILDER_PROFILE: true" in text}
    print(json.dumps(result,sort_keys=True)); return 0 if ids==[f"{i:02d}" for i in range(1,16)] and result["folded"] else 1
if __name__ == "__main__": raise SystemExit(main())
