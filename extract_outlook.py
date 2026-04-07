#!/usr/bin/env python3
# extract_outlook.py
"""Extract email data from a macOS Outlook 15 profile to .eml / .mbox / attachments."""
from __future__ import annotations

import argparse, logging, pathlib, sys, sqlite3, urllib.parse
from parsers.message import parse_message
from parsers.source import parse_source
from parsers.attachment import parse_attachment
from writer import EmlWriter
from flatten_attachments import run as flatten_attachments

log = logging.getLogger("extract_outlook")

PROFILE_BASE = pathlib.Path.home() / (
    "Library/Group Containers/UBF8T346G9.Office/Outlook"
    "/Outlook 15 Profiles/Main Profile"
)

def walk_files(directory: pathlib.Path, suffix: str):
    """Yield all files with given suffix under directory."""
    if not directory.exists():
        return
    for subdir in sorted(directory.iterdir()):
        if subdir.is_dir():
            for f in sorted(subdir.iterdir()):
                if f.suffix == suffix:
                    yield f

def load_metadata(profile: pathlib.Path) -> dict[str, dict]:
    """Load email metadata from Outlook.sqlite into a lookup dictionary."""
    db_path = profile / "Data" / "Outlook.sqlite"
    if not db_path.exists():
        log.warning("Metadata database not found at %s", db_path)
        return {}
    
    log.info("Loading metadata from %s...", db_path)
    meta = {}
    try:
        # Use mode=ro for read-only access to avoid locking issues
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT PathToDataFile, Message_SenderList, Message_SenderAddressList, 
                   Message_DisplayTo, Message_ToRecipientAddressList, Message_CCRecipientAddressList,
                   Message_NormalizedSubject, Message_TimeReceived, Message_TimeSent, Message_MessageID,
                   Threads_ThreadID
            FROM Mail
        """)
        for row in cursor:
            path, s_list, s_addr, t_list, t_addr, cc_addr, subj, date_ts, sent_ts, msg_id, thread_id = row
            if not path: continue
            uuid = pathlib.Path(path).stem
            meta[uuid] = {
                "from": s_addr or s_list,
                "to": t_addr or t_list,
                "cc": cc_addr,
                "subject": subj,
                "date": date_ts,
                "sent_date": sent_ts,
                "message_id": msg_id,
                "thread_id": thread_id,
                "attachments": []
            }
            
        # Add attachment mappings
        cursor.execute("""
            SELECT m.PathToDataFile, b.PathToDataFile 
            FROM Mail_OwnedBlocks mo 
            JOIN Mail m ON mo.Record_RecordID = m.Record_RecordID 
            JOIN Blocks b ON mo.BlockID = b.BlockID 
            WHERE b.BlockTag = 1098151011
        """)
        for m_path, b_path in cursor:
            if not m_path or not b_path: continue
            m_uuid = pathlib.Path(m_path).stem
            if m_uuid in meta:
                meta[m_uuid]["attachments"].append(urllib.parse.unquote(b_path))
        
        conn.close()
    except Exception as exc:
        log.error("Failed to load metadata: %s", exc)
    
    log.info("Loaded metadata for %d messages.", len(meta))
    return meta

def run(output_dir: pathlib.Path, include_attachments: bool, profile: pathlib.Path, max_messages: int = 0, flatten: bool = False, debug_unparseable: bool = False) -> None:
    """Run extraction with optional message limit."""
    metadata = load_metadata(profile)
    writer = EmlWriter(output_dir)
    error_log_path = output_dir / "extract.log"
    
    success_count = 0
    write_ok = True
    with open(error_log_path, "w", encoding="utf-8") as error_log:
        # --- Phase 2: .olk15MsgSource files (processed first for deduplication priority) ---
        src_dir = profile / "Data" / "Message Sources"
        log.info("Counting files in %s...", src_dir)
        total = sum(1 for _ in walk_files(src_dir, ".olk15MsgSource"))
        src_files = walk_files(src_dir, ".olk15MsgSource")
        log.info("Processing %d .olk15MsgSource files...", total)
        ok = skipped = errors = 0
        for i, path in enumerate(src_files, 1):
            if max_messages > 0 and success_count >= max_messages:
                log.info("Reached max messages limit (%d), stopping sources phase", max_messages)
                break
            if i % 500 == 0:
                log.info("  sources: %d/%d (ok=%d skipped=%d errors=%d)", i, total, ok, skipped, errors)
            try:
                mime = parse_source(path.read_bytes())
                if mime is None:
                    skipped += 1
                    error_log.write(f"SKIP\tsources\t{path.name}\tno MIME markers found\n")
                    continue
                if writer.write_eml(path.stem, mime, source="sources"):
                    ok += 1
                    success_count += 1
            except Exception as exc:
                errors += 1
                error_log.write(f"ERROR\tsources\t{path.name}\t{exc}\n")
        log.info("Sources done: ok=%d skipped=%d errors=%d", ok, skipped, errors)

        # --- Phase 1: .olk15Message files ---
        msg_dir = profile / "Data" / "Messages"
        log.info("Counting files in %s...", msg_dir)
        total = sum(1 for _ in walk_files(msg_dir, ".olk15Message"))
        msg_files = walk_files(msg_dir, ".olk15Message")
        log.info("Processing %d .olk15Message files...", total)
        ok = skipped = errors = 0
        for i, path in enumerate(msg_files, 1):
            if max_messages > 0 and success_count >= max_messages:
                log.info("Reached max messages limit (%d), stopping messages phase", max_messages)
                break
            if i % 1000 == 0:
                log.info("  messages: %d/%d (ok=%d skipped=%d errors=%d)", i, total, ok, skipped, errors)
            try:
                msg_meta = metadata.get(path.stem)
                
                # Pre-load attachment bytes
                att_data_list = []
                if msg_meta and msg_meta.get("attachments"):
                    for att_path in msg_meta["attachments"]:
                        full_att_path = profile / "Data" / att_path
                        if full_att_path.exists():
                            res = parse_attachment(full_att_path.read_bytes())
                            if res:
                                att_data_list.extend(res)
                            
                mime = parse_message(path.read_bytes(), msg_meta, att_data_list)
                if mime is None:
                    skipped += 1
                    error_log.write(f"SKIP\tmessages\t{path.name}\tno content found\n")
                    continue
                if writer.write_eml(path.stem, mime, source="messages"):
                    ok += 1
                    success_count += 1
            except Exception as exc:
                errors += 1
                error_log.write(f"ERROR\tmessages\t{path.name}\t{exc}\n")
        log.info("Messages done: ok=%d skipped=%d errors=%d", ok, skipped, errors)

        # --- Phase 3 (optional): .olk15MsgAttachment files ---
        if include_attachments:
            att_dir = profile / "Data" / "Message Attachments"
            log.info("Counting files in %s...", att_dir)
            total = sum(1 for _ in walk_files(att_dir, ".olk15MsgAttachment"))
            att_files = walk_files(att_dir, ".olk15MsgAttachment")
            log.info("Processing %d .olk15MsgAttachment files...", total)
            ok = skipped = errors = 0
            debug_dir = output_dir / "debug_attachments"
            for i, path in enumerate(att_files, 1):
                if i % 1000 == 0:
                    log.info("  attachments: %d/%d (ok=%d skipped=%d errors=%d)", i, total, ok, skipped, errors)
                try:
                    result = parse_attachment(path.read_bytes())
                    if result is None:
                        skipped += 1
                        error_log.write(f"SKIP\tattachments\t{path.name}\tempty or invalid file\n")
                        continue
                    if isinstance(result, tuple) and result[0] is None:
                        _, reason = result
                        skipped += 1
                        error_log.write(f"SKIP\tattachments\t{path.name}\t{reason}\n")
                        if debug_unparseable:
                            debug_dir.mkdir(parents=True, exist_ok=True)
                            debug_path = debug_dir / f"{path.name}.bin"
                            debug_path.write_bytes(path.read_bytes()[:256])
                        continue
                    for filename, _content_type, data in result:
                        writer.write_attachment(path.stem, filename, data)
                    ok += 1
                except Exception as exc:
                    errors += 1
                    error_log.write(f"ERROR\tattachments\t{path.name}\t{exc}\n")
            log.info("Attachments done: ok=%d skipped=%d errors=%d", ok, skipped, errors)

        if flatten:
            att_dir = output_dir / "attachments"
            flat_dir = att_dir / "flat"
            if att_dir.exists():
                log.info("Flattening attachments to %s...", flat_dir)
                flatten_attachments(att_dir, flat_dir)
            else:
                log.warning("No attachments directory found, skipping flatten")

        writer.flush()
    if max_messages > 0 and success_count >= max_messages:
        log.info("Extraction complete. Reached limit of %d messages", max_messages)
    else:
        log.info("Extraction complete. Total messages written: %d", success_count)
    log.info("Done. Output in: %s", output_dir)

def main():
    parser = argparse.ArgumentParser(description="Extract Outlook 15 email data to .eml / .mbox")
    parser.add_argument("--output", "-o", default="./output", help="Output directory (default: ./output)")
    parser.add_argument("--profile", default=str(PROFILE_BASE), help="Path to Outlook 15 Main Profile directory")
    parser.add_argument("--attachments-to-disk", action="store_true", help="Extract attachment files to disk")
    parser.add_argument("--include-attachments", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--flatten-attachments", action="store_true", help="Flatten and deduplicate extracted attachments into attachments/flat/")
    parser.add_argument("--debug-unparseable", action="store_true", help="Save first 256 bytes of unparseable attachments for analysis")
    parser.add_argument("--max-messages", "-n", type=int, default=0, help="Maximum number of messages to extract (0=unlimited)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.include_attachments:
        logging.basicConfig(
            level=logging.DEBUG if args.verbose else logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
        )
        log.warning("--include-attachments is deprecated, use --attachments-to-disk instead")
    else:
        logging.basicConfig(
            level=logging.DEBUG if args.verbose else logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
        )

    output_dir = pathlib.Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = pathlib.Path(args.profile).resolve()

    if not profile.exists():
        log.error("Profile directory not found: %s", profile)
        sys.exit(1)

    run(output_dir, args.attachments_to_disk or args.include_attachments, profile, args.max_messages, flatten=args.flatten_attachments, debug_unparseable=args.debug_unparseable)

if __name__ == "__main__":
    main()
