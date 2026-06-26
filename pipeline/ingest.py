# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""
Ingest script to catalog images from person folders.
Walks library root, extracts metadata, and stores in database.
"""

import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path

from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from .database import Database, Image
from .paths import relative_to_content

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}


class Ingester:
    def __init__(self, db: Database, library_root: str):
        self.db = db
        self.library_root = Path(library_root)
        self.processed_count = 0
        self.skipped_count = 0
        self.error_count = 0

    def calculate_hash(self, filepath: Path) -> str:
        """Calculate SHA256 hash of file."""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def extract_metadata(self, filepath: Path) -> dict[str, object]:
        """Extract basic metadata from image file."""
        metadata = {
            "path": relative_to_content(filepath),
            "filename": filepath.name,
            "directory": relative_to_content(filepath.parent),
            "filesize": filepath.stat().st_size,
            "format": filepath.suffix.lower().lstrip("."),
            "created_at": datetime.fromtimestamp(filepath.stat().st_ctime),
            "modified_at": datetime.fromtimestamp(filepath.stat().st_mtime),
            "has_metadata": False,
        }

        # Derive person + media_type from the normalized layout:
        #   content/library/<person>/<_unsorted|videos|legacy-rating>/<hash>.<ext>
        # Rating is decoupled from placement (Wave 2c): it is a removable label
        # set, no longer a directory level, so ingest does NOT write a rating.
        parts = filepath.relative_to(self.library_root).parts
        if parts:
            metadata["person"] = parts[0]
        bucket = parts[1] if len(parts) > 1 else ""
        metadata["media_type"] = "video" if bucket == "videos" else "image"

        # Try to get image dimensions
        try:
            with PILImage.open(filepath) as img:
                metadata["width"] = img.width
                metadata["height"] = img.height

                # Try to get EXIF data
                try:
                    import exifread

                    with open(filepath, "rb") as f:
                        tags = exifread.process_file(f, details=False)
                        if tags:
                            metadata["has_metadata"] = True
                except Exception:
                    pass
        except (UnidentifiedImageError, OSError) as e:
            logger.warning(f"Could not open image {filepath}: {e}")
            metadata["width"] = 0
            metadata["height"] = 0

        return metadata

    def process_file(self, filepath: Path, session) -> Image | None:
        """Process a single image file."""
        try:
            # Skip hidden files
            if filepath.name.startswith("."):
                return None

            # Check extension
            if filepath.suffix.lower() not in SUPPORTED_EXTENSIONS:
                return None

            # Calculate hash
            file_hash = self.calculate_hash(filepath)

            # Extract metadata
            metadata = self.extract_metadata(filepath)
            metadata["file_hash"] = file_hash

            # Check if already in database
            existing = session.query(Image).filter_by(file_hash=file_hash).first()
            if existing:
                logger.debug(f"File already in database: {filepath}")
                self.skipped_count += 1
                return existing

            # Add to database
            image = self.db.add_image(session, metadata)
            self.processed_count += 1

            if self.processed_count % 100 == 0:
                logger.info(f"Processed {self.processed_count} files...")

            return image

        except Exception as e:
            logger.error(f"Error processing {filepath}: {e}")
            self.error_count += 1
            return None

    def scan_directory(self, path: Path | None = None) -> tuple[int, int, int]:
        """
        Scan directory recursively and ingest all images.
        Returns: (processed, skipped, error)
        """
        if path is None:
            path = self.library_root

        session = self.db.get_session()

        try:
            # Walk through directory
            for root, _dirs, files in os.walk(path):
                logger.info(f"Scanning {root}...")

                for file in files:
                    filepath = Path(root) / file
                    self.process_file(filepath, session)

                # Commit periodically
                if self.processed_count % 500 == 0:
                    session.commit()

            # Final commit
            session.commit()

        finally:
            session.close()

        return self.processed_count, self.skipped_count, self.error_count

    def scan_person_folders(self) -> dict[str, tuple[int, int, int]]:
        """Scan only person folders."""
        results = {}

        # List person folders
        person_folders = [d for d in self.library_root.iterdir() if d.is_dir()]

        for folder in person_folders:
            logger.info(f"Processing person folder: {folder.name}")

            # Reset counters for this folder
            self.processed_count = 0
            self.skipped_count = 0
            self.error_count = 0

            processed, skipped, error = self.scan_directory(folder)
            results[folder.name] = (processed, skipped, error)

            logger.info(
                f"Finished {folder.name}: {processed} new, {skipped} skipped, {error} errors"
            )

        return results


def main():
    """Command-line interface."""
    import argparse
    from pathlib import Path

    from pipeline.settings import settings_from_config_file

    parser = argparse.ArgumentParser(description="Ingest images into database")
    parser.add_argument("--config", default="config.yaml", help="Configuration file")
    parser.add_argument("--person", help="Specific person folder to scan")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Resolve config via the typed settings layer (honors --config / env).
    cfg = settings_from_config_file(args.config)

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Initialize database
    db_path = cfg.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = Database(str(db_path))
    ingester = Ingester(db, str(cfg.library_root))

    if args.person:
        # Scan specific person folder
        person_path = Path(cfg.library_root) / args.person
        if person_path.exists():
            processed, skipped, error = ingester.scan_directory(person_path)
            print(f"Results for {args.person}:")
            print(f"  New: {processed}")
            print(f"  Skipped (duplicates): {skipped}")
            print(f"  Errors: {error}")
        else:
            print(f"Person folder not found: {args.person}")
    else:
        # Scan all person folders
        results = ingester.scan_person_folders()

        print("\nIngestion Summary:")
        print("=" * 50)
        total_new = total_skipped = total_error = 0

        for person, (new, skipped, error) in results.items():
            print(
                f"{person:20} | New: {new:5} | Skipped: {skipped:5} | Errors: {error:3}"
            )
            total_new += new
            total_skipped += skipped
            total_error += error

        print("=" * 50)
        print(
            f"Total:               | New: {total_new:5} | Skipped: {total_skipped:5} | Errors: {total_error:3}"
        )


if __name__ == "__main__":
    main()
