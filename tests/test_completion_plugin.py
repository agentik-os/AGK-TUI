import asyncio
import importlib.util
import inspect
import json
import os
import sys
from pathlib import Path

sys.path.insert(0,"/opt/agk-terminal/hermes-agent")

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/"hermes/plugins/agentik_os/completion.py"
PLUGIN_INIT=MODULE.parent/"__init__.py"
NUTRITION_COMMAND=MODULE.parent/"nutrition_command.py"


def load():
 spec=importlib.util.spec_from_file_location("completion_plugin_test",MODULE); assert spec and spec.loader
 module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def test_pre_llm_hook_archives_original_user_prompt_once(tmp_path,monkeypatch):
 module=load(); monkeypatch.setenv("HERMES_HOME",str(tmp_path/".hermes")); monkeypatch.setenv("AGK_TERMINAL_ROOT",str(ROOT))
 module.archive_before_execution(session_id="s1",platform="discord",turn_id="t1",user_message="Do A, B and C")
 module.archive_before_execution(session_id="s1",platform="discord",turn_id="t1",user_message="Do A, B and C")
 db=module.open_store().db
 assert db.execute("SELECT COUNT(*) FROM prompts").fetchone()[0]==1
 assert Path(db.execute("SELECT content_path FROM prompts").fetchone()[0]).read_text()=="Do A, B and C"


def test_completion_prompt_accepts_runtime_session_context():
 module=load()
 prompt=module.completion_prompt({"platform":"discord","profile":"operator"})
 assert "Gauntlet/Loop-Graph" in prompt
 assert "permit_done=true" in prompt
 assert "apply a canonical todo plan before operational work" in prompt
 assert "enumerate every currently known action upfront" in prompt
 assert "revise the visible plan when scope changes" in prompt


def test_completion_handler_accepts_registry_context_and_executes(tmp_path,monkeypatch):
 module=load()
 monkeypatch.setenv("HERMES_HOME",str(tmp_path/".hermes"))
 monkeypatch.setenv("AGK_TERMINAL_ROOT",str(ROOT))
 monkeypatch.syspath_prepend("/opt/agk-terminal/hermes-agent")
 result=asyncio.run(module.handle_completion({
  "action":"archive","text":"Verify the graph loop","source":"test",
  "session_id":"session-1","profile":"operator",
 },task_id="registry-task"))
 assert json.loads(result)["success"] is True


def test_add_requirement_reports_missing_graph_identifiers_without_keyerror(tmp_path,monkeypatch):
 module=load()
 monkeypatch.setenv("HERMES_HOME",str(tmp_path/".hermes"))
 monkeypatch.setenv("AGK_TERMINAL_ROOT",str(ROOT))
 monkeypatch.syspath_prepend("/opt/agk-terminal/hermes-agent")
 result=asyncio.run(module.handle_completion({
  "action":"add_requirement","mission_id":"MISS-test","text":"Verify recovery",
 }))
 payload=json.loads(result)
 assert payload["error"]=="prompt_id is required for add_requirement"
 assert "KeyError" not in payload["error"]


def test_completion_tool_is_registered_as_async():
 source=PLUGIN_INIT.read_text()
 block=source[source.index('name="agk_completion"'):source.index('emoji="✓"')]
 assert "handler=handle_completion" in block
 assert "is_async=True" in block


def test_plan_mode_blocks_operational_tool_until_todo_plan_is_applied():
 module=load()
 blocked=module.require_plan_before_work(
  tool_name="terminal",args={"command":"pytest"},turn_id="turn-1"
 )
 assert blocked["action"]=="block"
 assert "todo" in blocked["message"]
 assert module.require_plan_before_work(
  tool_name="todo",args={"todos":[{"id":"test","content":"Run tests","status":"in_progress"}]},turn_id="turn-1"
 ) is None
 blocked=module.require_plan_before_work(
  tool_name="terminal",args={"command":"pytest"},turn_id="turn-1"
 )
 assert blocked["action"]=="block"
 module.record_applied_plan(
  tool_name="todo",turn_id="turn-1",status="ok",
  result='{"todos":[{"id":"test","content":"Run tests","status":"in_progress"}]}'
 )
 assert module.require_plan_before_work(
  tool_name="terminal",args={"command":"pytest"},turn_id="turn-1"
 ) is None


def test_plan_mode_allows_skill_loading_before_plan_but_not_work():
 module=load()
 assert module.require_plan_before_work(
  tool_name="skill_view",args={"name":"verified-builder"},turn_id="turn-2"
 ) is None
 blocked=module.require_plan_before_work(
  tool_name="write_file",args={"path":"x"},turn_id="turn-2"
 )
 assert blocked["action"]=="block"


def test_plan_mode_hook_is_registered():
 source=PLUGIN_INIT.read_text()
 assert 'ctx.register_hook("pre_tool_call", require_plan_before_work)' in source
 assert 'ctx.register_hook("post_tool_call", record_applied_plan)' in source


def test_failed_or_invalid_todo_never_authorizes_operational_work():
 module=load()
 module.record_applied_plan(
  tool_name="todo",turn_id="failed-turn",status="error",
  result='{"todos":[{"id":"x","content":"Work","status":"in_progress"}]}'
 )
 assert module.require_plan_before_work(
  tool_name="terminal",args={"command":"true"},turn_id="failed-turn"
 )["action"]=="block"
 module.record_applied_plan(
  tool_name="todo",turn_id="invalid-turn",status="ok",
  result='{"todos":[{"id":"x","content":"A","status":"in_progress"},{"id":"y","content":"B","status":"in_progress"}]}'
 )
 assert module.require_plan_before_work(
  tool_name="terminal",args={"command":"true"},turn_id="invalid-turn"
 )["action"]=="block"


def test_completion_storage_uses_context_local_profile_home(tmp_path,monkeypatch):
 module=load()
 from hermes_constants import reset_hermes_home_override,set_hermes_home_override
 default_home=tmp_path/"default"; profile_home=tmp_path/"profiles"/"nutrition-os"
 monkeypatch.setenv("HERMES_HOME",str(default_home))
 monkeypatch.setenv("AGK_TERMINAL_ROOT",str(ROOT))
 token=set_hermes_home_override(profile_home)
 try:
  module.archive_before_execution(session_id="s",platform="discord",turn_id="t",user_message="Profile plan")
  store=module.open_store()
  assert store.db_path==profile_home/"completion"/"completion.db"
  row=store.db.execute("SELECT profile FROM prompts").fetchone()
  assert row[0]=="nutrition-os"
  store.close()
 finally:
  reset_hermes_home_override(token)
 assert not (default_home/"completion"/"completion.db").exists()


def test_nutrition_commands_are_scoped_to_canonical_private_profile():
 source=PLUGIN_INIT.read_text()
 assert "def _dedicated_nutrition_profile()" in source
 assert '/home/private/.hermes/profiles/nutrition-os' in source
 assert "if _dedicated_nutrition_profile():" in source
 assert '/home/operator/.hermes/profiles/nutrition' not in source
 command=NUTRITION_COMMAND.read_text()
 assert '/home/private/.hermes/profiles/nutrition-os' in command
 assert '/home/operator/.hermes/profiles/nutrition' not in command
