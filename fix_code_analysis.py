"""Fix code_analysis.py to add path validation with os.path.realpath()"""

path = "/mnt/Main/appdata/ember/backend/routers/code_analysis.py"
with open(path, "r") as f:
    content = f.read()

# Add path validation imports and helper after the existing imports
old_imports = '''logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["analysis"])'''

new_imports = '''logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["analysis"])

# ---------------------------------------------------------------------------
# Security: path allowlist
# ---------------------------------------------------------------------------

ALLOWED_ANALYSIS_PREFIXES = (
    "/mnt/Main/appdata/",
    "/mnt/Main/inop/",
    "/mnt/Main/scripts/",
)


def _validate_analysis_path(path: str) -> None:
    """Validate that path is within allowed directories.

    Uses os.path.realpath() to resolve symlinks and '..' components.
    Raises HTTPException if path is outside the allowlist or contains null bytes.
    """
    import os
    if not path or "\\x00" in path:
        raise HTTPException(status_code=400, detail="Invalid path: null bytes not allowed")
    resolved = os.path.realpath(path)
    if not any(resolved.startswith(prefix) for prefix in ALLOWED_ANALYSIS_PREFIXES):
        raise HTTPException(
            status_code=403,
            detail=f"Path outside allowed directories: {path}",
        )'''

if old_imports in content:
    content = content.replace(old_imports, new_imports)
    print("OK: Added path validation helper to code_analysis.py")
else:
    print("ERROR: Could not find imports section")

# Add validation to full_analysis endpoint
old_scan = '''async def full_analysis(request: AnalysisRequest):
    """Run full project analysis: AST scan + complexity + dependency graph."""
    from ..code_analysis.analyzer import CodeAnalyzer

    try:'''

new_scan = '''async def full_analysis(request: AnalysisRequest):
    """Run full project analysis: AST scan + complexity + dependency graph."""
    _validate_analysis_path(request.project_root)
    from ..code_analysis.analyzer import CodeAnalyzer

    try:'''

if old_scan in content:
    content = content.replace(old_scan, new_scan)
    print("OK: Added validation to full_analysis")
else:
    print("ERROR: Could not find full_analysis endpoint")

# Add validation to analysis_summary endpoint
old_summary = '''async def analysis_summary(request: AnalysisRequest):
    """Get a compact summary of project analysis."""
    from ..code_analysis.analyzer import CodeAnalyzer

    try:'''

new_summary = '''async def analysis_summary(request: AnalysisRequest):
    """Get a compact summary of project analysis."""
    _validate_analysis_path(request.project_root)
    from ..code_analysis.analyzer import CodeAnalyzer

    try:'''

if old_summary in content:
    content = content.replace(old_summary, new_summary)
    print("OK: Added validation to analysis_summary")
else:
    print("ERROR: Could not find analysis_summary endpoint")

# Add validation to analyze_file endpoint
old_file = '''async def analyze_file(request: FileAnalysisRequest):
    """Analyze a single file (complexity, structure, imports)."""
    from ..code_analysis.analyzer import CodeAnalyzer

    try:'''

new_file = '''async def analyze_file(request: FileAnalysisRequest):
    """Analyze a single file (complexity, structure, imports)."""
    _validate_analysis_path(request.project_root)
    # Validate combined path to prevent file_path traversal out of project_root
    import os
    combined = os.path.realpath(os.path.join(request.project_root, request.file_path))
    resolved_root = os.path.realpath(request.project_root)
    if not combined.startswith(resolved_root + "/") and combined != resolved_root:
        raise HTTPException(status_code=403, detail="file_path escapes project_root")
    from ..code_analysis.analyzer import CodeAnalyzer

    try:'''

if old_file in content:
    content = content.replace(old_file, new_file)
    print("OK: Added validation to analyze_file")
else:
    print("ERROR: Could not find analyze_file endpoint")

# Add validation to complexity_only endpoint
old_complexity = '''async def complexity_only(request: ComplexityRequest):
    """Calculate complexity metrics for a project."""
    from pathlib import Path
    from ..code_analysis.complexity import calculate_complexity'''

new_complexity = '''async def complexity_only(request: ComplexityRequest):
    """Calculate complexity metrics for a project."""
    _validate_analysis_path(request.project_root)
    from pathlib import Path
    from ..code_analysis.complexity import calculate_complexity'''

if old_complexity in content:
    content = content.replace(old_complexity, new_complexity)
    print("OK: Added validation to complexity_only")
else:
    print("ERROR: Could not find complexity_only endpoint")

# Add validation to dependencies_only endpoint
old_deps = '''async def dependencies_only(request: DependencyRequest):
    """Build import dependency graph for a project."""
    from pathlib import Path
    from ..code_analysis.dependencies import build_dependency_graph'''

new_deps = '''async def dependencies_only(request: DependencyRequest):
    """Build import dependency graph for a project."""
    _validate_analysis_path(request.project_root)
    from pathlib import Path
    from ..code_analysis.dependencies import build_dependency_graph'''

if old_deps in content:
    content = content.replace(old_deps, new_deps)
    print("OK: Added validation to dependencies_only")
else:
    print("ERROR: Could not find dependencies_only endpoint")

with open(path, "w") as f:
    f.write(content)
print("DONE: code_analysis.py written")
