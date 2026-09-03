#!/usr/bin/env python3
from pathlib import Path
import argparse, json, re, zipfile
OS_ID='media-os'; VERSION='1.1.0'; REQUIRED=['manifest.yaml', 'profile/distribution.yaml', 'profile/SOUL.md', 'agents/nano-director.md', 'agents/nanoteam.yaml', 'skills/order.yaml', 'programs/os_program.py', 'contracts/tools.yaml', 'contracts/scopes.yaml', 'contracts/providers.yaml', 'workflow.yaml', 'automations/automations.yaml', 'evals/cases.json', 'commands/discord.yaml', 'commands/HOW_TO_PIN.md', 'doctor.py', 'rollback.py', 'research/14_BUILDER_HANDOFF.md', 'research/15_INPUTS_LEDGER.json', 'CONTRACT.json']
def main():
 p=argparse.ArgumentParser(); p.add_argument("--package-root",type=Path,default=Path(__file__).resolve().parent); p.add_argument("--recovery-extraction",action="store_true"); a=p.parse_args(); root=a.package_root.resolve(); findings=[]
 for rel in REQUIRED:
  if not (root/rel).is_file(): findings.append({"code":"MISSING_FILE","path":rel})
 try:
  c=json.loads((root/"CONTRACT.json").read_text());
  if c.get("os_id")!=OS_ID or c.get("version")!=VERSION or c.get("tenant")!="AGK": findings.append({"code":"CONTRACT_IDENTITY"})
  if c.get("gates",{}).get("release")!="unpassed": findings.append({"code":"RELEASE_GATE"})
 except Exception as e: findings.append({"code":"CONTRACT_PARSE","error":type(e).__name__})
 try:
  t=(root/"research/14_BUILDER_HANDOFF.md").read_text(); ids=re.findall(r"^### INPUT-(\d{2})\b",t,re.M)
  if ids != [f"{i:02d}" for i in range(1,16)] or "FOLDED_BY_BUILDER_PROFILE: true" not in t: findings.append({"code":"HANDOFF"})
 except Exception as e: findings.append({"code":"HANDOFF_READ","error":type(e).__name__})
 if not a.recovery_extraction:
  archive=root/"recovery"/f"{OS_ID}-{VERSION}.zip"
  try:
   with zipfile.ZipFile(archive) as z: names=z.namelist()
   if not {"CONTRACT.json","doctor.py","rollback.py"} <= set(names): findings.append({"code":"RECOVERY_CONTENT"})
  except Exception as e: findings.append({"code":"RECOVERY_READ","error":type(e).__name__})
 out={"status":"PASS" if not findings else "FAIL","os_id":OS_ID,"version":VERSION,"mode":"recovery-extraction" if a.recovery_extraction else "package","findings":findings}; print(json.dumps(out,sort_keys=True)); return 0 if not findings else 1
if __name__=="__main__": raise SystemExit(main())
