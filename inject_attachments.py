import sqlite3, pathlib, logging, argparse, mimetypes, email, email.policy

log = logging.getLogger("inject_attachments")

def get_attachment_mapping(profile: pathlib.Path) -> dict[str, list[str]]:
    db_path = profile / "Data" / "Outlook.sqlite"
    meta = {}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cursor = conn.cursor()
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
        b_uuid = pathlib.Path(b_path).stem
        meta.setdefault(m_uuid, []).append(b_uuid)
    return meta

def run(profile: pathlib.Path, target_dir: pathlib.Path, att_dir: pathlib.Path, test_uuid: str | None = None):
    mapping = get_attachment_mapping(profile)
    
    if not target_dir.exists():
        log.error("Target directory not found at %s", target_dir)
        return
        
    files_to_process = [target_dir / f"{test_uuid}.eml"] if test_uuid else target_dir.glob("*.eml")
    
    for eml_path in files_to_process:
        if not eml_path.exists(): continue
        m_uuid = eml_path.stem
        if m_uuid not in mapping: continue
        
        try:
            mime_bytes = eml_path.read_bytes()
            msg = email.message_from_bytes(mime_bytes, policy=email.policy.default)
            
            # If it already has multiple parts, we assume it was a MsgSource or already injected
            if msg.is_multipart():
                continue
                
            injected_any = False
            for b_uuid in mapping[m_uuid]:
                att_folder = att_dir / b_uuid
                if not att_folder.exists():
                    continue
                for file_path in att_folder.iterdir():
                    if not file_path.is_file(): continue
                    
                    if not injected_any:
                        msg.make_mixed()
                        injected_any = True
                        
                    data = file_path.read_bytes()
                    ctype, _ = mimetypes.guess_type(file_path.name)
                    if ctype is None: ctype = "application/octet-stream"
                    maintype, subtype = ctype.split("/", 1)
                    
                    msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=file_path.name)
            
            if injected_any:
                eml_path.write_bytes(msg.as_bytes())
                log.info("Injected attachments into %s", eml_path.name)
                
        except Exception as exc:
            log.error("Failed to process %s: %s", m_uuid, exc)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--attachments", required=True)
    parser.add_argument("--test-uuid", help="Only run on this specific UUID")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(pathlib.Path(args.profile), pathlib.Path(args.target), pathlib.Path(args.attachments), args.test_uuid)
