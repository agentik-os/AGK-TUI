#!/usr/bin/env python3
from __future__ import annotations
import fcntl,json,os,pwd,shlex,subprocess,time
from pathlib import Path
USERS=("operator","agentik","mission","private")
SAFE="/usr/local/lib/agk-terminal/scripts/station_safe_gateway_reload.py"
REPORT=Path("/var/lib/agk-station/discord-design-activation-c3b7615.json")
DEADLINE=time.monotonic()+86400

def call(cmd): return subprocess.run(cmd,text=True,capture_output=True,check=False)
def user_systemctl(user,uid,*args): return call(["sudo","-u",user,"env",f"XDG_RUNTIME_DIR=/run/user/{uid}",f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus","systemctl","--user",*args])
def state(home):
 try: return json.loads((Path(home)/"gateway_state.json").read_text())
 except Exception: return {}
def current(row):
 s=state(row['home']); pid=int(s.get('pid') or 0)
 try: ok=pid>0 and Path(f'/proc/{pid}').stat().st_ctime >= (Path(row['home'])/'plugins/platforms/discord/adapter.py').stat().st_mtime
 except OSError: ok=False
 return ok,s
def inventory():
 rows=[]
 for user in USERS:
  pw=pwd.getpwnam(user); uid=pw.pw_uid
  q=user_systemctl(user,uid,'list-units','--type=service','--state=running','--no-legend','--plain','hermes-gateway*.service')
  for line in q.stdout.splitlines():
   unit=line.split()[0] if line.split() else ''
   if not unit: continue
   e=user_systemctl(user,uid,'show',unit,'-p','Environment','--value'); vals=shlex.split(e.stdout.strip())
   home=next((v.split('=',1)[1] for v in vals if v.startswith('HERMES_HOME=')),f'{pw.pw_dir}/.hermes')
   rows.append({'user':user,'uid':uid,'unit':unit,'home':home})
 return rows

def write_report(targets,results,pending):
 REPORT.parent.mkdir(parents=True,exist_ok=True)
 tmp=REPORT.with_suffix('.tmp'); tmp.write_text(json.dumps({'targets':len(targets),'results':results,'pending':list(pending.values())},indent=2)+'\n'); os.replace(tmp,REPORT)

lock_path=Path('/run/agk-station/discord-design-activation-c3b7615.lock'); lock_path.parent.mkdir(parents=True,exist_ok=True)
with lock_path.open('w') as lock:
 fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
 targets=inventory(); results=[]; pending={}
 for row in targets:
  ok,s=current(row)
  if ok: results.append({**row,'status':'already-current','pid':int(s.get('pid') or 0),'verified':True})
  else: pending[(row['user'],row['unit'])]=row
 write_report(targets,results,pending)
 while pending and time.monotonic()<DEADLINE:
  progressed=False
  for key,row in list(pending.items()):
   before=state(row['home']); active=before.get('active_agents')
   if active!=0: continue
   cp=call(['/usr/bin/python3',SAFE,'--user',row['user'],'--unit',row['unit'],'--hermes-home',row['home'],'--timeout','1800'])
   try: payload=json.loads((cp.stdout.strip().splitlines() or ['{}'])[-1])
   except Exception: payload={'status':'invalid-output','returncode':cp.returncode}
   ok,after=current(row)
   if payload.get('status') in {'reloaded','not-running'} and (payload.get('status')=='not-running' or ok):
    results.append({**row,**payload,'gateway_state':after.get('gateway_state'),'verified':True}); pending.pop(key); progressed=True
   elif payload.get('status') not in {'busy','already-in-progress'}:
    results.append({**row,**payload,'verified':False}); pending.pop(key); progressed=True
   write_report(targets,results,pending)
  if pending: time.sleep(10 if progressed else 30)
 for row in pending.values(): results.append({**row,'status':'timeout','active_agents':state(row['home']).get('active_agents'),'verified':False})
 write_report(targets,results,{})
 failed=[r for r in results if not r.get('verified')]
 print(json.dumps({'targets':len(targets),'verified':len(results)-len(failed),'failed':len(failed)}))
 raise SystemExit(1 if failed else 0)
