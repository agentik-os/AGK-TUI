#!/usr/bin/env python3
"""Confirmed, transactional rollback for one TENANT=AGK OS (builder-os 0.5.0 -> 0.4.4).

Dry-run (default) mutates nothing and reports READY/BLOCKED. --execute requires the exact
--confirm builder-os@0.4.4 plus --profile-snapshot; it atomically reactivates the previous
immutable package, restores the profile snapshot, rewrites only the builder-os assignment row,
flips registry status, and preserves rollback history. Any failure restores the pre-state."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, stat, tempfile
import yaml
OS_ID='builder-os'; PREVIOUS='0.4.4'
REQUIRED=("config.yaml","distribution.yaml","SOUL.md")

def emit(plan,status,reason=None,code=0):
 plan["status"]=status
 if reason: plan["reason"]=reason
 print(json.dumps(plan,sort_keys=True)); return code

def regular_file(path): return path.is_file() and not path.is_symlink()

def package_checksum(root):
 if not root.is_dir() or root.is_symlink(): raise ValueError("unsafe previous package")
 digest=hashlib.sha256(); count=0
 for path in sorted(root.rglob("*")):
  if path.is_symlink(): raise ValueError("symlink in previous package")
  if not path.is_file(): continue
  relative=path.relative_to(root).as_posix().encode(); content=path.read_bytes(); count+=1
  digest.update(len(relative).to_bytes(4,"big")); digest.update(relative); digest.update(len(content).to_bytes(8,"big")); digest.update(content)
 if not count: raise ValueError("empty previous package")
 return digest.hexdigest()

def atomic_bytes(path,data):
 st=path.stat(); f=tempfile.NamedTemporaryFile("wb",dir=path.parent,prefix=f".{path.name}.",delete=False); q=Path(f.name)
 try:
  with f: f.write(data); f.flush(); os.fsync(f.fileno())
  os.chmod(q,stat.S_IMODE(st.st_mode)); os.chown(q,st.st_uid,st.st_gid); os.replace(q,path)
 finally: q.unlink(missing_ok=True)

def encoded_yaml(value): return yaml.safe_dump(value,sort_keys=False,allow_unicode=True).encode()
def encoded_json(value): return (json.dumps(value,indent=2,sort_keys=True)+"\n").encode()

def main():
 p=argparse.ArgumentParser(); p.add_argument("--registry",type=Path,default=Path("/opt/agentik/os-registry")); p.add_argument("--assignments",type=Path,default=Path("/etc/agentik/operator-os/assignments.yaml")); p.add_argument("--canonical-root",type=Path,default=Path("/usr/local/lib/agk-terminal/os-packages")); p.add_argument("--profiles-root",type=Path,default=Path.home()/".hermes/profiles"); p.add_argument("--profile-snapshot",type=Path); p.add_argument("--confirm"); p.add_argument("--execute",action="store_true"); a=p.parse_args()
 package=a.registry/"packages"/OS_ID/PREVIOUS; index=a.registry/"state/index.json"; plan={"os_id":OS_ID,"target_version":PREVIOUS,"package":str(package),"assignments":str(a.assignments),"mode":"execute" if a.execute else "dry-run"}
 try:
  calculated=package_checksum(package); state=json.loads(index.read_text()); entries=[row for row in state.get("packages",[]) if row.get("id")==OS_ID and row.get("version")==PREVIOUS]
 except Exception as exc: return emit(plan,"BLOCKED",f"previous package preflight failed: {type(exc).__name__}",2)
 if len(entries)!=1 or not entries[0].get("checksum"): return emit(plan,"BLOCKED","previous package registry entry missing",2)
 if entries[0]["checksum"]!=calculated: return emit(plan,"BLOCKED","previous package checksum mismatch",2)
 plan["package_checksum"]=calculated
 if not a.execute:
  if a.profile_snapshot:
   snapshot=a.profile_snapshot if a.profile_snapshot.name==OS_ID else a.profile_snapshot/OS_ID
   plan["profile_snapshot_ready"]=snapshot.is_dir() and not snapshot.is_symlink() and all(regular_file(snapshot/name) for name in REQUIRED)
  return emit(plan,"READY",code=0)
 if a.confirm!=f"{OS_ID}@{PREVIOUS}": return emit(plan,"BLOCKED","exact --confirm is required",2)
 if not a.profile_snapshot: return emit(plan,"BLOCKED","--profile-snapshot is required",2)
 snapshot=a.profile_snapshot if a.profile_snapshot.name==OS_ID else a.profile_snapshot/OS_ID
 if not snapshot.is_dir() or snapshot.is_symlink() or not all(regular_file(snapshot/name) for name in REQUIRED): return emit(plan,"BLOCKED","profile snapshot is incomplete or unsafe",2)
 try: assignment_original=a.assignments.read_bytes(); doc=yaml.safe_load(assignment_original) or {}
 except Exception as exc: return emit(plan,"BLOCKED",f"assignments preflight failed: {type(exc).__name__}",2)
 rows=[row for row in doc.get("assignments",[]) if str(row.get("os","")).split("@",1)[0]==OS_ID]
 if len(rows)!=1: return emit(plan,"BLOCKED","assignment cardinality is not one",2)
 current=str(rows[0]["os"]).split("@",1)[-1]; target=a.canonical_root/OS_ID; profile=a.profiles_root/OS_ID
 if not target.is_dir() or target.is_symlink(): return emit(plan,"BLOCKED","current canonical package is absent or unsafe",2)
 if not profile.is_dir() or profile.is_symlink() or not all(regular_file(profile/name) for name in REQUIRED): return emit(plan,"BLOCKED","current profile is absent or unsafe",2)
 history=a.canonical_root/".rollback-history"/f"{OS_ID}-{current}"; profile_history=a.profiles_root/".rollback-history"/f"{OS_ID}-{current}"
 if history.exists() or profile_history.exists(): return emit(plan,"BLOCKED","rollback history target already exists",2)
 index_original=index.read_bytes(); rows[0]["os"]=f"{OS_ID}@{PREVIOUS}"
 for row in state.get("packages",[]):
  if row.get("id")==OS_ID: row["status"]="active" if row.get("version")==PREVIOUS else "superseded"
 stage=Path(tempfile.mkdtemp(prefix=f".{OS_ID}-{PREVIOUS}.",dir=a.canonical_root)); replaced=False; profile_changed=False; assignment_changed=False; index_changed=False
 try:
  shutil.copytree(package,stage,dirs_exist_ok=True); history.parent.mkdir(parents=True,exist_ok=True); os.replace(target,history); os.replace(stage,target); replaced=True
  profile_history.mkdir(parents=True,exist_ok=False)
  for name in REQUIRED:
   shutil.copy2(profile/name,profile_history/name); replacement=profile/f".{name}.rollback"; shutil.copy2(snapshot/name,replacement); os.replace(replacement,profile/name)
  profile_changed=True; atomic_bytes(a.assignments,encoded_yaml(doc)); assignment_changed=True; atomic_bytes(index,encoded_json(state)); index_changed=True
 except Exception as exc:
  restore_errors=[]
  if index_changed:
   try: atomic_bytes(index,index_original)
   except Exception as restore: restore_errors.append(f"index:{type(restore).__name__}")
  if assignment_changed:
   try: atomic_bytes(a.assignments,assignment_original)
   except Exception as restore: restore_errors.append(f"assignments:{type(restore).__name__}")
  if profile_history.exists():
   try:
    for name in REQUIRED:
     if regular_file(profile_history/name): shutil.copy2(profile_history/name,profile/name)
    shutil.rmtree(profile_history)
   except Exception as restore: restore_errors.append(f"profile:{type(restore).__name__}")
  if replaced and history.exists():
   try:
    if target.exists(): shutil.rmtree(target)
    os.replace(history,target)
   except Exception as restore: restore_errors.append(f"package:{type(restore).__name__}")
  if restore_errors: plan["restore_errors"]=restore_errors
  return emit(plan,"FAIL",type(exc).__name__,1)
 finally:
  if stage.exists(): shutil.rmtree(stage)
 plan.update(previous_active=current,profile_snapshot=str(snapshot),registry_checksum_verified=True); return emit(plan,"PASS",code=0)
if __name__=="__main__": raise SystemExit(main())
