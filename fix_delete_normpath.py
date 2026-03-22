"""Fix remaining normpath in _exec_delete_file to use os.path.realpath()"""

path = "/mnt/Main/appdata/ember/backend/tools/definitions.py"
with open(path, "r") as f:
    content = f.read()

old = '''    # Safety: block deletion of top-level allowed paths
    import posixpath
    normalized = posixpath.normpath(path)
    dangerous = ["/mnt/Main/staging", "/mnt/Main/media", "/mnt/Main/appdata",
                 "/mnt/Main/downloads", "/mnt/Main", "/mnt"]
    if normalized in dangerous:
        return {"error": f"Refusing to delete top-level directory: {path}"}'''

new = '''    # Safety: block deletion of top-level allowed paths
    import os as _os
    resolved = _os.path.realpath(path)
    dangerous = ["/mnt/Main/staging", "/mnt/Main/media", "/mnt/Main/appdata",
                 "/mnt/Main/downloads", "/mnt/Main", "/mnt"]
    if resolved in dangerous:
        return {"error": f"Refusing to delete top-level directory: {path}"}'''

if old in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print("OK: Fixed normpath in _exec_delete_file")
else:
    print("ERROR: Could not find old normpath block")
