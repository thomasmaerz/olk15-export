# test_harness.py
import os
import pathlib
import random
import logging
import sys
from extract_outlook import walk_files, PROFILE_BASE, load_metadata
from parsers.message import parse_message
from parsers.source import parse_source
from writer import EmlWriter

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("test_harness")

TNEF_UUIDS = [
    "E46D06BE-9D95-4E93-8D4B-E54C56FE1E56",
    "BD4522ED-BB2D-4ADA-AB4D-CE43FE6B2676",
    "E1A8A4DD-C3A9-4E14-82AB-B88052F913D5",
    "3C2B1891-9E55-4914-9098-6656A74A1D39",
    "20E086DB-CD14-4476-B7E4-C201EBC24CA4",
    "B2F321B3-6723-4425-BAE6-16389B833B34",
    "6B38ECDF-F843-4270-A683-DD504FCC9A32",
    "48B4DA3C-2749-4EC4-B09E-28EC0AD71B7B",
    "FB6E754A-9B70-4B56-9947-25748D12396D",
    "9C1A7DAB-6F7A-48B6-952A-A795C0FCF16A"
]

def run_test(sample_size=100):
    output_dir = pathlib.Path("./output_test_harness").resolve()
    if output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    
    metadata = load_metadata(PROFILE_BASE)
    writer = EmlWriter(output_dir)
    profile = PROFILE_BASE
    
    msg_dir = profile / "Data" / "Messages"
    src_dir = profile / "Data" / "Message Sources"
    
    # Collect some random files
    all_msgs = list(walk_files(msg_dir, ".olk15Message"))
    all_srcs = list(walk_files(src_dir, ".olk15MsgSource"))
    
    selected_msgs = random.sample(all_msgs, min(sample_size // 2, len(all_msgs)))
    selected_srcs = random.sample(all_srcs, min(sample_size // 2, len(all_srcs)))
    
    # Add TNEF ones specifically if they exist
    tnef_files = []
    for uuid in TNEF_UUIDS:
        # We need to find the actual file path. Since they are nested in S0, S1...
        # We'll just search for them in the walk results
        for f in all_msgs:
            if f.stem == uuid:
                tnef_files.append(f)
                break
    
    log.info("Processing %d messages, %d sources, %d known TNEF files", 
             len(selected_msgs), len(selected_srcs), len(tnef_files))
    
    # Process them
    for f in tnef_files + selected_msgs:
        try:
            msg_meta = metadata.get(f.stem)
            mime = parse_message(f.read_bytes(), msg_meta)
            if mime:
                writer.write_eml(f.stem, mime, source="messages")
        except Exception as e:
            log.error("Failed to process %s: %s", f.name, e)
            
    for f in selected_srcs:
        try:
            mime = parse_source(f.read_bytes())
            if mime:
                writer.write_eml(f.stem, mime, source="sources")
        except Exception as e:
            log.error("Failed to process %s: %s", f.name, e)
            
    writer.flush()
    log.info("Test harness complete. Output in %s", output_dir)
    
    # Basic assertions
    import email
    from email.policy import default
    maildir_new = output_dir / "Maildir" / "cur"
    count = 0
    empty_bodies = 0
    tnef_remnants = 0
    
    content_types = {}
    
    for f in maildir_new.iterdir():
        count += 1
        raw = f.read_bytes()
        msg = email.message_from_bytes(raw, policy=default)
        ct = msg.get_content_type()
        content_types[ct] = content_types.get(ct, 0) + 1
        
        body = msg.get_body(preferencelist=('html', 'plain'))
        body_content = ""
        if body:
            try:
                body_content = body.get_content().strip()
            except Exception as e:
                log.warning("get_content failed for %s: %s", f.name, e)
                body_content = ""
        
        if not body or not body_content:
            # If it's a known non-text type, it's expected
            if ct not in ["text/calendar", "application/pdf", "image/jpeg"]:
                empty_bodies += 1
                log.warning("Empty body in %s (CT: %s)", f.name, ct)
        
        # Check for winmail.dat remnants
        for part in msg.walk():
            fn = part.get_filename() or ""
            if fn.lower() == "winmail.dat":
                tnef_remnants += 1
                log.warning("TNEF remnant found in %s", f.name)
                
    log.info("Validation: Total=%d, EmptyBodies=%d, TNEFRemnants=%d", 
             count, empty_bodies, tnef_remnants)
    log.info("Content-Types: %s", content_types)

if __name__ == "__main__":
    run_test(500)
