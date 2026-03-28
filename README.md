# olk15-export

A set of Python scripts to extract emails and attachments from macOS Outlook 15 (`.olk15Message`, `.olk15MsgSource`, and `.olk15MsgAttachment` files) into standard `.eml`, `Maildir`, or `.mbox` formats.

**⚠️ Experimental State:** This tool is currently in an experimental state and is provided as-is. Bug reports, issues, and pull requests are highly encouraged!

## Features
- Bypasses missing header issues by reading `Outlook.sqlite` metadata dynamically.
- Native injection of attachments directly into the generated `multipart/mixed` `.eml` files.
- Includes standalone scripts to fix existing extractions and flatten complex attachment folders.

## Tools
1. `extract_outlook.py`: The core extractor. Run this against your Mac Outlook profile.
2. `inject_attachments.py`: Post-processing script to embed detached attachments into an existing `Maildir`.
3. `flatten_attachments.py`: Utility to deduplicate (via MD5 hash) and flatten nested attachment folders into a single directory, resolving filename collisions automatically.
4. `rebuild_mbox.py`: Utility to stitch extracted `.eml` files into a single `.mbox` archive.

## Usage
Extract a profile into a Maildir directory:
```bash
python3 extract_outlook.py --profile "~/Library/Group Containers/UBF8T346G9.Office/Outlook/Outlook 15 Profiles/Main Profile" --output ./output
```

## License
MIT License
