# test_targeted.py
import os
import pathlib
import logging
import sys
from extract_outlook import walk_files, PROFILE_BASE, load_metadata
from parsers.message import parse_message
from writer import EmlWriter

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("test_targeted")

TARGET_UUIDS = [
    "90CB96B1-7763-44E2-A160-5F1BD4AB278E", # CMMC Follow up
    "580921C4-759F-4711-8013-ECF0AEDF6C1E", # Verify Employee Directory
    "ED0E0CA1-D1E6-43B8-AF31-F3BBBCE864E1", # Projecturf
    "E4815477-4734-4674-8BC9-ED440CE1B6F2"  # Archibus Demo #3
]

def run_test():
    output_dir = pathlib.Path("./output_targeted_test").resolve()
    if output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    
    metadata = load_metadata(PROFILE_BASE)
    writer = EmlWriter(output_dir)
    
    msg_dir = PROFILE_BASE / "Data" / "Messages"
    
    # Find the actual files
    all_msgs = list(walk_files(msg_dir, ".olk15Message"))
    
    found_count = 0
    for uuid in TARGET_UUIDS:
        target_file = None
        for f in all_msgs:
            if f.stem == uuid:
                target_file = f
                break
        
        if target_file:
            log.info("Processing target: %s (%s)", uuid, target_file.name)
            msg_meta = metadata.get(uuid)
            mime = parse_message(target_file.read_bytes(), msg_meta)
            if mime:
                writer.write_eml(uuid, mime, source="messages")
                found_count += 1
        else:
            log.warning("Could not find file for UUID: %s", uuid)
            
    writer.flush()
    log.info("Targeted test complete. Processed %d files. Output in %s", found_count, output_dir)

if __name__ == "__main__":
    run_test()
