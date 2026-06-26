"""
Grid generation using FFmpeg for creating image collages.
Supports various layouts and can generate grids from database queries.
"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from pipeline.paths import resolve_image_path

logger = logging.getLogger(__name__)


class GridGenerator:
    """Generate image grids using FFmpeg."""

    def __init__(self, ffmpeg_path: str | None = None):
        self.ffmpeg_path = ffmpeg_path or "ffmpeg"
        self.temp_dir = None

    def check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available."""
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired, FileNotFoundError:
            logger.error(f"FFmpeg not found at {self.ffmpeg_path}")
            return False

    def create_temp_dir(self) -> Path:
        """Create temporary directory for processing."""
        if not self.temp_dir or not self.temp_dir.exists():
            self.temp_dir = Path(tempfile.mkdtemp(prefix="grid_"))
        return self.temp_dir

    def cleanup(self):
        """Clean up temporary files."""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
            self.temp_dir = None

    def resize_images(
        self, image_paths: list[Path], target_size: tuple[int, int] = (512, 512)
    ) -> list[Path]:
        """Resize images to consistent dimensions."""
        resized_paths = []
        temp_dir = self.create_temp_dir()

        for i, img_path in enumerate(image_paths):
            output_path = temp_dir / f"resized_{i}{img_path.suffix}"

            # Use FFmpeg to resize
            cmd = [
                self.ffmpeg_path,
                "-y",  # Overwrite output
                "-i",
                str(img_path),
                "-vf",
                f"scale={target_size[0]}:{target_size[1]}:force_original_aspect_ratio=decrease,"
                f"pad={target_size[0]}:{target_size[1]}:(ow-iw)/2:(oh-ih)/2:black",
                str(output_path),
            ]

            try:
                subprocess.run(cmd, capture_output=True, check=True)
                resized_paths.append(output_path)
                logger.debug(f"Resized {img_path} to {target_size}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to resize {img_path}: {e}")
                # Use original as fallback
                resized_paths.append(img_path)

        return resized_paths

    def create_grid_xstack(
        self,
        image_paths: list[Path],
        layout: str = "2x2",
        output_path: Path | None = None,
    ) -> Path | None:
        """
        Create grid using FFmpeg's xstack filter.

        Args:
            image_paths: List of image paths
            layout: Grid layout like "2x2", "3x3", "4x4"
            output_path: Output file path (optional)

        Returns:
            Path to generated grid or None if failed
        """
        if not image_paths:
            logger.error("No images provided for grid")
            return None

        if not self.check_ffmpeg():
            return None

        try:
            # Parse layout
            rows, cols = map(int, layout.split("x"))
            total_cells = rows * cols

            # Limit to available images
            images_to_use = image_paths[:total_cells]
            if len(images_to_use) < total_cells:
                logger.warning(
                    f"Only {len(images_to_use)} images available for {total_cells} cell grid"
                )

            # Create output path if not provided
            if output_path is None:
                temp_dir = self.create_temp_dir()
                output_path = temp_dir / f"grid_{layout}_{len(images_to_use)}.jpg"
            else:
                output_path = Path(output_path)

            # Build FFmpeg command
            cmd = [self.ffmpeg_path, "-y"]

            # Add input files
            for img_path in images_to_use:
                cmd.extend(["-i", str(img_path)])

            # Build xstack filter
            filter_parts = []
            for i in range(len(images_to_use)):
                row = i // cols
                col = i % cols
                filter_parts.append(f"[{i}:v]")

            filter_str = "".join(filter_parts)
            filter_str += f"xstack=inputs={len(images_to_use)}:layout="

            # Build layout string
            layout_parts = []
            cell_width = 512  # Default cell width
            cell_height = 512  # Default cell height

            for i in range(len(images_to_use)):
                row = i // cols
                col = i % cols
                x_pos = col * cell_width
                y_pos = row * cell_height
                layout_parts.append(f"{x_pos}_{y_pos}")

            filter_str += "|".join(layout_parts)

            cmd.extend(["-filter_complex", filter_str])
            cmd.append(str(output_path))

            # Run FFmpeg
            logger.info(f"Creating {layout} grid with {len(images_to_use)} images...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                logger.info(f"Grid created: {output_path}")
                return output_path
            else:
                logger.error(f"FFmpeg failed: {result.stderr}")
                return None

        except Exception as e:
            logger.error(f"Error creating grid: {e}")
            return None

    def create_grid_montage(
        self,
        image_paths: list[Path],
        layout: str = "2x2",
        output_path: Path | None = None,
    ) -> Path | None:
        """
        Create grid using ImageMagick montage (alternative).
        FFmpeg's xstack can be finicky, so this is a fallback.
        """
        try:
            # Check if montage is available
            result = subprocess.run(["montage", "--version"], capture_output=True)
            if result.returncode != 0:
                logger.warning("ImageMagick montage not available, using xstack")
                return self.create_grid_xstack(image_paths, layout, output_path)

            # Create output path
            if output_path is None:
                temp_dir = self.create_temp_dir()
                output_path = temp_dir / f"grid_{layout}_{len(image_paths)}.jpg"
            else:
                output_path = Path(output_path)

            # Build montage command
            cmd = ["montage"]

            # Add input files
            for img_path in image_paths:
                cmd.append(str(img_path))

            # Parse layout
            rows, cols = map(int, layout.split("x"))

            cmd.extend(
                [
                    "-geometry",
                    "+0+0",  # No spacing between images
                    "-tile",
                    f"{cols}x{rows}",
                    str(output_path),
                ]
            )

            logger.info(
                f"Creating montage {layout} grid with {len(image_paths)} images..."
            )
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                logger.info(f"Montage grid created: {output_path}")
                return output_path
            else:
                logger.error(f"Montage failed: {result.stderr}")
                # Fall back to xstack
                return self.create_grid_xstack(image_paths, layout, output_path)

        except Exception as e:
            logger.error(f"Error creating montage grid: {e}")
            return self.create_grid_xstack(image_paths, layout, output_path)

    def create_contact_sheet(
        self,
        video_path: Path,
        rows: int = 4,
        cols: int = 4,
        interval: int = 10,
        output_path: Path | None = None,
    ) -> Path | None:
        """
        Create video contact sheet (grid of thumbnails).

        Args:
            video_path: Path to video file
            rows: Number of rows
            cols: Number of columns
            interval: Seconds between thumbnails
            output_path: Output file path

        Returns:
            Path to contact sheet or None if failed
        """
        if not self.check_ffmpeg():
            return None

        try:
            if output_path is None:
                temp_dir = self.create_temp_dir()
                output_path = temp_dir / f"contact_{video_path.stem}.jpg"
            else:
                output_path = Path(output_path)

            # Create contact sheet via interval sampling so each tile is a
            # DISTINCT time sample. The old `thumbnail` filter picked one
            # representative frame for the whole clip, tiling duplicates;
            # `fps=1/interval` samples one frame every `interval` seconds.
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-i",
                str(video_path),
                "-vf",
                f"fps=1/{interval},scale=320:-1,tile={cols}x{rows}",
                "-frames:v",
                "1",
                str(output_path),
            ]

            logger.info(f"Creating contact sheet for {video_path}...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode == 0:
                logger.info(f"Contact sheet created: {output_path}")
                return output_path
            else:
                logger.error(f"Contact sheet failed: {result.stderr}")
                return None

        except Exception as e:
            logger.error(f"Error creating contact sheet: {e}")
            return None

    def generate_from_query(
        self,
        db_session,
        query_filters: dict[str, Any],
        layout: str = "3x3",
        limit: int = 9,
    ) -> Path | None:
        """
        Generate grid from database query.

        Args:
            db_session: Database session
            query_filters: Filters for image query
            layout: Grid layout
            limit: Maximum number of images

        Returns:
            Path to generated grid
        """
        from .database import Image

        try:
            # Query database
            query = db_session.query(Image)

            for key, value in query_filters.items():
                if key == "person":
                    if isinstance(value, list):
                        query = query.filter(Image.person.in_(value))
                    else:
                        query = query.filter(Image.person == value)
                elif key == "rating":
                    # Join with tags table
                    from .database import Tag

                    query = query.join(Tag).filter(
                        Tag.category == "rating", Tag.value == value
                    )

            images = query.limit(limit).all()

            if not images:
                logger.warning(f"No images found for filters: {query_filters}")
                return None

            # Get file paths
            image_paths = [resolve_image_path(img.path) for img in images]

            # Create grid
            return self.create_grid_montage(image_paths, layout)

        except Exception as e:
            logger.error(f"Error generating grid from query: {e}")
            return None


def main():
    """Test grid generation."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Generate image grids")
    parser.add_argument("--images", nargs="+", help="Image files")
    parser.add_argument("--layout", default="2x2", help="Grid layout (e.g., 2x2, 3x3)")
    parser.add_argument("--output", help="Output file")
    parser.add_argument("--video", help="Create contact sheet from video")
    parser.add_argument("--rows", type=int, default=4, help="Rows for contact sheet")
    parser.add_argument("--cols", type=int, default=4, help="Columns for contact sheet")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(level=logging.INFO)

    generator = GridGenerator()

    if args.video:
        # Create video contact sheet
        video_path = Path(args.video)
        if not video_path.exists():
            print(f"Video not found: {video_path}")
            sys.exit(1)

        output = generator.create_contact_sheet(
            video_path, rows=args.rows, cols=args.cols, output_path=args.output
        )

        if output:
            print(f"Contact sheet created: {output}")
        else:
            print("Failed to create contact sheet")
            sys.exit(1)

    elif args.images:
        # Create image grid
        image_paths = [Path(img) for img in args.images]

        # Check files exist
        for img_path in image_paths:
            if not img_path.exists():
                print(f"Image not found: {img_path}")
                sys.exit(1)

        output = generator.create_grid_montage(
            image_paths, layout=args.layout, output_path=args.output
        )

        if output:
            print(f"Grid created: {output}")
        else:
            print("Failed to create grid")
            sys.exit(1)
    else:
        print("Error: Specify either --images or --video")
        sys.exit(1)

    # Cleanup
    generator.cleanup()


if __name__ == "__main__":
    main()
