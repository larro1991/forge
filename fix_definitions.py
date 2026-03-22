"""Patch definitions.py to add destructive tool guardrails."""
import sys

filepath = "/mnt/Main/appdata/ember/backend/tools/definitions.py"

with open(filepath, "r") as f:
    content = f.read()

# 1. Add DESTRUCTIVE_TOOLS set and rate-limiting infrastructure after ALLOWED_COMMAND_PREFIXES
imports_addition = '''

# ---------------------------------------------------------------------------
# Destructive tool guardrails
# ---------------------------------------------------------------------------

DESTRUCTIVE_TOOLS = {"write_file", "delete_file", "move_file"}
MAX_DESTRUCTIVE_PER_MESSAGE = 3

# Per-message destructive operation counter.
# Reset by the chat router before each new user message via reset_destructive_counter().
import threading as _threading
_destructive_lock = _threading.Lock()
_destructive_count = 0


def reset_destructive_counter():
    """Reset the destructive operation counter. Called by chat router per message."""
    global _destructive_count
    with _destructive_lock:
        _destructive_count = 0


def _check_destructive_limit(tool_name: str) -> Optional[str]:
    """Increment counter and return error message if limit exceeded, else None."""
    global _destructive_count
    with _destructive_lock:
        if _destructive_count >= MAX_DESTRUCTIVE_PER_MESSAGE:
            logger.warning(
                "Destructive tool limit reached (%d/%d). Blocked: %s",
                _destructive_count, MAX_DESTRUCTIVE_PER_MESSAGE, tool_name,
            )
            return (
                f"Safety limit: max {MAX_DESTRUCTIVE_PER_MESSAGE} destructive operations "
                f"per message reached. Please send a new message to continue."
            )
        _destructive_count += 1
        return None


def is_destructive_tool(name: str) -> bool:
    """Return True if the named tool is tagged as destructive."""
    return name in DESTRUCTIVE_TOOLS
'''

marker = '    "zpool status", "zpool list", "zfs list",\n]'

if marker not in content:
    print("ERROR: Could not find ALLOWED_COMMAND_PREFIXES marker", file=sys.stderr)
    sys.exit(1)

content = content.replace(marker, marker + imports_addition)

# 2. Update execute_tool() to enforce the limit and audit-log destructive operations
old_execute = '''async def execute_tool(name: str, arguments: Dict) -> Dict:
    """Execute a tool by name with the given arguments.

    Returns {"result": ...} on success or {"error": ...} on failure.
    """
    executor = _EXECUTORS.get(name)
    if not executor:
        return {"error": f"Unknown tool: {name}"}

    try:
        logger.info("Executing tool: %s(%s)", name, json.dumps(arguments)[:200])
        result = await executor(arguments)'''

new_execute = '''async def execute_tool(name: str, arguments: Dict) -> Dict:
    """Execute a tool by name with the given arguments.

    Returns {"result": ...} on success or {"error": ...} on failure.
    Destructive tools (write_file, delete_file, move_file) are rate-limited
    to MAX_DESTRUCTIVE_PER_MESSAGE per chat message and audit-logged.
    """
    executor = _EXECUTORS.get(name)
    if not executor:
        return {"error": f"Unknown tool: {name}"}

    # Enforce destructive operation limit
    if name in DESTRUCTIVE_TOOLS:
        limit_err = _check_destructive_limit(name)
        if limit_err:
            return {"error": limit_err}

    try:
        # Audit-log destructive operations with full detail before execution
        if name in DESTRUCTIVE_TOOLS:
            logger.warning(
                "DESTRUCTIVE TOOL CALL: %s | args=%s",
                name, json.dumps(arguments),
            )

        logger.info("Executing tool: %s(%s)", name, json.dumps(arguments)[:200])
        result = await executor(arguments)'''

if old_execute not in content:
    print("ERROR: Could not find execute_tool marker", file=sys.stderr)
    sys.exit(1)

content = content.replace(old_execute, new_execute)

with open(filepath, "w") as f:
    f.write(content)

print("definitions.py patched successfully")
