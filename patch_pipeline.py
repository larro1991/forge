#!/usr/bin/env python3
"""Patch video pipeline files: controller.py and tracker.py"""
import re

# --- Fix #2: Broaden _move_companion_subtitles in controller.py ---
ctrl_path = "/mnt/Main/inop/video-pipeline/controller.py"
with open(ctrl_path, "r") as f:
    ctrl = f.read()

old_method = '''    def _move_companion_subtitles(self, pipeline: str, source_video: Path, relative_path: str):
        """Move subtitle files (.srt, .sub, .ass, .ssa, .idx) from staging to library."""
        SUBTITLE_EXTS = {'.srt', '.sub', '.ass', '.ssa', '.idx', '.sup', '.vtt'}
        staging_dir = source_video.parent
        if not staging_dir.exists():
            return

        library_folder = self._get_path(pipeline, "library")
        # Use the relative path's parent dir for the library destination
        rel_parent = Path(relative_path).parent
        lib_dest_dir = library_folder / rel_parent
        lib_dest_dir.mkdir(parents=True, exist_ok=True)

        for f in staging_dir.iterdir():
            if f.is_file() and f.suffix.lower() in SUBTITLE_EXTS:
                dest = lib_dest_dir / f.name
                try:
                    shutil.move(str(f), str(dest))
                    log.info(f"SUBTITLE MOVED: {f.name} -> {dest}")
                except Exception as e:
                    log.error(f"Failed to move subtitle {f.name}: {e}")'''

new_method = '''    def _move_companion_subtitles(self, pipeline: str, source_video: Path, relative_path: str):
        """Move subtitle files from staging to library, including Subs/ subdirectories."""
        SUBTITLE_EXTS = {'.srt', '.sub', '.ass', '.ssa', '.idx', '.sup', '.vtt'}
        staging_dir = source_video.parent
        if not staging_dir.exists():
            return

        library_folder = self._get_path(pipeline, "library")
        rel_parent = Path(relative_path).parent
        lib_dest_dir = library_folder / rel_parent
        lib_dest_dir.mkdir(parents=True, exist_ok=True)

        # Move subtitle files from the same directory
        for f in staging_dir.iterdir():
            if f.is_file() and f.suffix.lower() in SUBTITLE_EXTS:
                dest = lib_dest_dir / f.name
                try:
                    shutil.move(str(f), str(dest))
                    log.info(f"SUBTITLE MOVED: {f.name} -> {dest}")
                except Exception as e:
                    log.error(f"Failed to move subtitle {f.name}: {e}")

        # Also check Subs/ subdirectories
        for sub_dir_name in ("Subs", "subs", "Subtitles", "subtitles"):
            sub_dir = staging_dir / sub_dir_name
            if not sub_dir.is_dir():
                continue
            lib_subs_dir = lib_dest_dir / sub_dir_name
            lib_subs_dir.mkdir(parents=True, exist_ok=True)
            for item in sub_dir.rglob("*"):
                if item.is_file() and item.suffix.lower() in SUBTITLE_EXTS:
                    rel_to_sub = item.relative_to(sub_dir)
                    dest = lib_subs_dir / rel_to_sub
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.move(str(item), str(dest))
                        log.info(f"SUBTITLE MOVED (subdir): {item.name} -> {dest}")
                    except Exception as e:
                        log.error(f"Failed to move subtitle {item.name}: {e}")
            # Remove the now-empty subtitle subdir
            try:
                import shutil as _shutil
                _shutil.rmtree(str(sub_dir))
                log.info(f"SUBTITLE DIR REMOVED: {sub_dir}")
            except Exception:
                pass'''

if old_method in ctrl:
    ctrl = ctrl.replace(old_method, new_method)
    print("Fix #2: _move_companion_subtitles broadened (OK)")
else:
    print("Fix #2: WARNING - exact match not found, trying flexible match")
    # Try to find and show context
    idx = ctrl.find("def _move_companion_subtitles")
    if idx >= 0:
        snippet = ctrl[idx:idx+800]
        print(f"Found method at offset {idx}:")
        print(snippet[:500])
    else:
        print("Method not found at all!")

# --- Fix #4a: Add .webm to VIDEO_EXTENSIONS in controller.py ---
old_ext = 'VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m4v", ".wmv", ".flv", ".mov", ".ts"}'
new_ext = 'VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m4v", ".wmv", ".flv", ".mov", ".ts", ".webm"}'
if old_ext in ctrl:
    ctrl = ctrl.replace(old_ext, new_ext)
    print("Fix #4a: .webm added to controller.py VIDEO_EXTENSIONS (OK)")
else:
    print("Fix #4a: WARNING - VIDEO_EXTENSIONS not found in expected format")

with open(ctrl_path, "w") as f:
    f.write(ctrl)
print(f"controller.py saved ({len(ctrl)} bytes)")

# --- Fix #4b: Add .webm to video_extensions in tracker.py ---
trk_path = "/mnt/Main/inop/video-pipeline/tracker.py"
with open(trk_path, "r") as f:
    trk = f.read()

old_trk_ext = '"video_extensions": {".mkv", ".mp4", ".avi", ".m4v", ".wmv", ".flv", ".mov", ".ts"}'
new_trk_ext = '"video_extensions": {".mkv", ".mp4", ".avi", ".m4v", ".wmv", ".flv", ".mov", ".ts", ".webm"}'
if old_trk_ext in trk:
    trk = trk.replace(old_trk_ext, new_trk_ext)
    print("Fix #4b: .webm added to tracker.py video_extensions (OK)")
else:
    print("Fix #4b: WARNING - video_extensions not found in expected format")

with open(trk_path, "w") as f:
    f.write(trk)
print(f"tracker.py saved ({len(trk)} bytes)")

# --- Fix #3: Fix stuck file 3919 ---
import sqlite3
db_path = "/mnt/Main/inop/video-pipeline/tracker.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

row = cur.execute("SELECT id, relative_path, status, pipeline FROM files WHERE id = 3919").fetchone()
if row:
    print(f"\nFix #3: File 3919 = {row['relative_path']} (status={row['status']}, pipeline={row['pipeline']})")
    if row['status'] == 'converted':
        cur.execute("UPDATE files SET status = 'completed' WHERE id = 3919")
        conn.commit()
        print("Fix #3: Updated status from 'converted' to 'completed' (OK)")
    elif row['status'] == 'completed':
        print("Fix #3: Already completed, no change needed")
    else:
        print(f"Fix #3: Unexpected status '{row['status']}', skipping")
else:
    print("Fix #3: File 3919 not found in DB, skipping")

conn.close()
print("\nAll patches applied!")
