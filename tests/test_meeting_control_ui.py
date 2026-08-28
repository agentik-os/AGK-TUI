from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
MODULE = (
    ROOT / "hermes" / "plugins" / "platforms" / "discord" / "agk_meeting_control_ui.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("agk_meeting_control_ui_test", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_persistent_view_exposes_fixed_meeting_control_ids():
    module = load_module()
    view = module.MeetingControlView()
    assert view.timeout is None
    assert [item.custom_id for item in view.children] == [
        "agkmeet:refresh",
        "agkmeet:reschedule",
        "agkmeet:cancel",
        "agkmeet:granola",
    ]


def test_authorization_requires_exact_owner_guild_and_meetings_forum():
    module = load_module()
    good = SimpleNamespace(
        user=SimpleNamespace(id=1441423462492016821),
        guild_id=1541131439599386644,
        channel=SimpleNamespace(parent_id=1542526162062938152),
    )
    assert module.authorized(good) is True
    assert (
        module.authorized(SimpleNamespace(**{**good.__dict__, "guild_id": 1})) is False
    )
    assert (
        module.authorized(
            SimpleNamespace(**{**good.__dict__, "user": SimpleNamespace(id=1)})
        )
        is False
    )
    assert (
        module.authorized(
            SimpleNamespace(
                **{**good.__dict__, "channel": SimpleNamespace(parent_id=1)}
            )
        )
        is False
    )


def test_adapter_registers_meeting_view_only_in_operator_profile_block():
    source = (
        ROOT / "hermes" / "plugins" / "platforms" / "discord" / "adapter.py"
    ).read_text()
    assert "register_meeting_control" in source
    operator_block = source[
        source.index('if hermes_home == _Path("/home/operator/.hermes")') :
    ]
    assert "register_meeting_control(adapter_self._client)" in operator_block[:2500]


def test_context_resolution_uses_private_state_and_action_map(tmp_path: Path):
    module = load_module()
    state = tmp_path / "publication.json"
    registry = tmp_path / "registry.json"
    actions = tmp_path / "actions.json"
    state.write_text(
        json.dumps(
            {
                "schema": "agk.meeting-publication-state.v1",
                "surfaces": {},
                "posts": {
                    "1542526162062938152:meeting:abc": {
                        "thread_id": 123,
                        "message_id": 456,
                    }
                },
            }
        )
    )
    registry.write_text(
        json.dumps(
            {
                "schema": "agk.meeting-registry.v1",
                "meetings": [
                    {
                        "id": "meeting:abc",
                        "title": "Review",
                        "start": "2026-08-30T10:00:00Z",
                        "end": "2026-08-30T11:00:00Z",
                        "status": "scheduled",
                        "armed": True,
                        "join": None,
                        "source_refs": [],
                    }
                ],
            }
        )
    )
    actions.write_text(
        json.dumps(
            {
                "schema": "agk.meeting-actions.v1",
                "actions": {
                    "meeting:abc": [
                        {"source": "cal", "resource_id": "private", "account": "cal"}
                    ]
                },
            }
        )
    )

    context = module.resolve_context(
        123,
        publication_state=state,
        registry_path=registry,
        actions_path=actions,
    )

    assert context.meeting["id"] == "meeting:abc"
    assert context.bindings[0]["resource_id"] == "private"
