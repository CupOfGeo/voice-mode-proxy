from voice_mode_proxy.agent import spoken_tool, tool_target
from voice_mode_proxy.server import _spoken_text


def test_bash_uses_the_description():
    assert (
        spoken_tool("Bash", {"description": "find network interfaces"}) == "Running a command: find network interfaces."
    )
    assert spoken_tool("Bash", {}) == "Running a shell command."


def test_file_tools_name_the_file():
    assert spoken_tool("Edit", {"file_path": "/a/b/models.py"}) == "Editing models.py."
    assert spoken_tool("Read", {}) == "Reading a file."


def test_mcp_tools_name_the_server():
    assert spoken_tool("mcp__claude_docs__batch", {}) == "Using the claude docs tool."
    assert spoken_tool("Whatever", {}) == "Using Whatever."


def test_tool_events_are_spoken():
    assert _spoken_text({"type": "tool", "name": "Bash", "spoken": "Running tests."}) == "Running tests."
    assert _spoken_text({"type": "tool", "name": "Bash"}) == ""


def test_tool_target_falls_back_past_a_missing_description():
    assert tool_target("Bash", {"description": "find network interfaces"}) == "find network interfaces"
    assert tool_target("Bash", {"command": "ifconfig | grep\n inet"}) == "ifconfig | grep inet"
    assert tool_target("Read", {"file_path": "/a/b/models.py"}) == "/a/b/models.py"
    assert tool_target("TodoWrite", {"todos": []}) == ""
