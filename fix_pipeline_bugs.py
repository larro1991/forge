#!/usr/bin/env python3
"""Fix two pipeline bugs in tracker.py and controller.py"""

# ============================================================
# FIX 1: tracker.py — verify_outputs should fail stale converted files
# ============================================================
tracker_path = "/mnt/Main/inop/video-pipeline/tracker.py"
with open(tracker_path, "r") as f:
    tracker = f.read()

old_verify_tail = """                    log.info(f"OUTPUT VERIFIED: {f['relative_path']}")"""

new_verify_tail = """                    log.info(f"OUTPUT VERIFIED: {f['relative_path']}")
                else:
                    # No output found — check how long it has been converted
                    ended = f.get("conversion_ended_at")
                    if ended:
                        try:
                            ended_dt = datetime.fromisoformat(ended)
                            age_hours = (datetime.now() - ended_dt).total_seconds() / 3600
                            if age_hours > 2:
                                self.db.update_status(
                                    f["id"], "failed",
                                    error_message="No output in library after conversion"
                                )
                                self.db.log_event(
                                    f["id"], "VERIFY_FAILED",
                                    f"No output found {age_hours:.0f}h after conversion ended"
                                )
                                log.error(f"VERIFY FAILED: {f['relative_path']} — no output after {age_hours:.0f}h")
                                notify("Conversion Output Missing",
                                       f"{f['relative_path']} — converted but no output in library",
                                       "error")
                        except (ValueError, TypeError):
                            pass"""

# Find the exact spot — this is the last line of verify_outputs before archive_sources
# We need to match the line at the end of the "if not found:" block
marker = '                    log.info(f"OUTPUT VERIFIED: {f[\'relative_path\']}")\n\n    def archive_sources'

if marker in tracker:
    tracker = tracker.replace(marker,
        new_verify_tail + '\n\n    def archive_sources')
    print("FIX 1: verify_outputs — added stale-converted failure detection (OK)")
else:
    print("FIX 1: WARNING — exact marker not found, trying alternate")
    # Try finding the end of verify_outputs
    idx = tracker.find("    def archive_sources")
    if idx > 0:
        # Look backwards for the last line of verify_outputs
        pre = tracker[:idx]
        # Insert the else block before archive_sources
        insert_point = pre.rstrip()
        # Check if the block ends correctly
        if insert_point.endswith("log.info(f\"OUTPUT VERIFIED: {f['relative_path']}\")"):
            tracker = insert_point + "\n" + """                else:
                    # No output found — check how long it has been converted
                    ended = f.get("conversion_ended_at")
                    if ended:
                        try:
                            ended_dt = datetime.fromisoformat(ended)
                            age_hours = (datetime.now() - ended_dt).total_seconds() / 3600
                            if age_hours > 2:
                                self.db.update_status(
                                    f["id"], "failed",
                                    error_message="No output in library after conversion"
                                )
                                self.db.log_event(
                                    f["id"], "VERIFY_FAILED",
                                    f"No output found {age_hours:.0f}h after conversion ended"
                                )
                                log.error(f"VERIFY FAILED: {f['relative_path']} — no output after {age_hours:.0f}h")
                                notify("Conversion Output Missing",
                                       f"{f['relative_path']} — converted but no output in library",
                                       "error")
                        except (ValueError, TypeError):
                            pass
""" + tracker[idx:]
            print("FIX 1: verify_outputs — added via alternate method (OK)")
        else:
            print(f"FIX 1: Block doesn't end as expected. Last 100 chars: {insert_point[-100:]}")
    else:
        print("FIX 1: archive_sources not found!")

with open(tracker_path, "w") as f:
    f.write(tracker)
print(f"  tracker.py saved ({len(tracker)} bytes)")


# ============================================================
# FIX 2: controller.py — probe failures get distinct status
# ============================================================
ctrl_path = "/mnt/Main/inop/video-pipeline/controller.py"
with open(ctrl_path, "r") as f:
    ctrl = f.read()

old_probe = """        # Probe video for bitrate-aware transcoding gate
        probe_data = probe_video(str(source))
        self._store_probe_data(file_id, probe_data)

        needs_transcode, transcode_reason = should_transcode(probe_data)"""

new_probe = """        # Probe video for bitrate-aware transcoding gate
        probe_data = probe_video(str(source))
        self._store_probe_data(file_id, probe_data)

        if probe_data is None:
            # Probe failed — file may be corrupt. Flag it instead of blindly queuing.
            log.error(f"PROBE FAILED: {f['relative_path']} — file may be corrupt or unreadable")
            self.db.execute(
                "UPDATE files SET status = 'error', error_message = 'ffprobe failed — file may be corrupt', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (file_id,))
            self._commit()
            self._log_event(file_id, "PROBE_FAILED",
                            f"ffprobe could not read {f['relative_path']}")
            notify("Probe Failed", f"{f['filename']} — may be corrupt", "error")
            return False

        needs_transcode, transcode_reason = should_transcode(probe_data)"""

if old_probe in ctrl:
    ctrl = ctrl.replace(old_probe, new_probe)
    print("FIX 2: approve_file — probe failures now flagged as error (OK)")
else:
    print("FIX 2: WARNING — exact match not found for approve_file probe block")
    # Show what's there
    idx = ctrl.find("probe_data = probe_video")
    if idx >= 0:
        print(f"  Found at offset {idx}:")
        print(ctrl[idx-50:idx+300])

with open(ctrl_path, "w") as f:
    f.write(ctrl)
print(f"  controller.py saved ({len(ctrl)} bytes)")

print("\nAll fixes applied!")
