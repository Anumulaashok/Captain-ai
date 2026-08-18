"""core/permission_manager.py gates every risky tool. This session's fix made
code-executing tools (ALWAYS_REVIEW) re-prompt on every call instead of caching
approval for the whole session — these tests lock that behavior in so it can't
silently regress back to "approve once, run anything forever"."""
from core.permission_manager import PermissionManager, PERMISSION_REQUIRED, ALWAYS_REVIEW


def _manager_with_fake_ui(response: bool):
    calls = []

    def fake_ui(tool, name, desc):
        calls.append(tool)
        return response

    pm = PermissionManager()
    pm.set_request_fn(fake_ui)
    return pm, calls


def test_unlisted_tool_never_needs_permission():
    pm, calls = _manager_with_fake_ui(True)
    assert pm.request("web_search") is True
    assert calls == []


def test_normal_tool_caches_grant_after_first_approval():
    pm, calls = _manager_with_fake_ui(True)
    assert pm.request("file_controller") is True
    assert pm.request("file_controller") is True
    assert pm.request("file_controller") is True
    assert calls.count("file_controller") == 1


def test_normal_tool_caches_denial_after_first_refusal():
    pm, calls = _manager_with_fake_ui(False)
    assert pm.request("file_controller") is False
    assert pm.request("file_controller") is False
    assert calls.count("file_controller") == 1


def test_always_review_tool_prompts_on_every_call():
    pm, calls = _manager_with_fake_ui(True)
    for _ in range(5):
        assert pm.request("dev_agent") is True
    assert calls.count("dev_agent") == 5


def test_always_review_tools_are_the_code_executing_ones():
    # Locks in which tools get re-prompted — if a new code-executing tool is added,
    # it must be added to ALWAYS_REVIEW explicitly, not silently inherit caching.
    assert ALWAYS_REVIEW == {"dev_agent", "code_helper", "generated_code"}


def test_code_helper_is_actually_gated():
    # Regression test: code_helper was missing from PERMISSION_REQUIRED entirely
    # until this session, meaning it ran with NO permission check at all.
    assert "code_helper" in PERMISSION_REQUIRED


def test_no_request_fn_registered_defaults_to_allow():
    # Headless/test contexts with no UI callback shouldn't hard-block — matches
    # existing behavior for every other tool.
    pm = PermissionManager()
    assert pm.request("dev_agent") is True
    assert pm.request("file_controller") is True
