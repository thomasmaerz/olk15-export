import argparse, pathlib, hashlib, shutil, logging

log = logging.getLogger("flatten")

def get_hash(path: pathlib.Path) -> str:
    hasher = hashlib.md5()
    # Read in chunks to avoid memory issues with large files
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def run(source: pathlib.Path, dest: pathlib.Path):
    dest.mkdir(parents=True, exist_ok=True)
    seen_hashes = set()
    
    # Grab all files in all subdirectories
    files = [f for f in source.rglob('*') if f.is_file()]
    log.info("Found %d files to process", len(files))
    
    moved = 0
    deleted = 0
    
    for i, f in enumerate(files, 1):
        if i % 1000 == 0:
            log.info("Processed %d/%d files...", i, len(files))
            
        try:
            file_hash = get_hash(f)
            
            if file_hash in seen_hashes:
                # Exact duplicate, safely delete it
                f.unlink()
                deleted += 1
            else:
                seen_hashes.add(file_hash)
                
                # Not a duplicate, move it to the flat directory
                base_name = f.name
                new_name = base_name
                counter = 1
                
                # Handle filename collisions (Approach B)
                while (dest / new_name).exists():
                    new_name = f"{f.stem}_{counter}{f.suffix}"
                    counter += 1
                    
                shutil.move(str(f), str(dest / new_name))
                moved += 1
        except Exception as exc:
            log.error("Failed to process %s: %s", f, exc)
            
    log.info("Done! Moved %d unique files. Deleted %d exact duplicates.", moved, deleted)
    
    # Cleanup all the empty UUID folders left behind
    log.info("Cleaning up empty directories...")
    # walk back from subdirectories upwards
    for dir_path in sorted(source.rglob('*'), key=lambda x: len(x.parts), reverse=True):
        if dir_path.is_dir():
            try:
                if not any(dir_path.iterdir()):
                    dir_path.rmdir()
            except Exception as exc:
                log.error("Failed to remove directory %s: %s", dir_path, exc)
            
    # Remove the parent source directory if it is completely empty
    if source.exists() and not any(source.iterdir()):
        source.rmdir()
        log.info("Deleted completely empty source directory %s", source)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--dest", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(pathlib.Path(args.source).resolve(), pathlib.Path(args.dest).resolve())
