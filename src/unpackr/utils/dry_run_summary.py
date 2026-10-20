"""
Dry-run summary output for Unpackr.
User Experience Layer: Improved Dry-Run Output

Collects planned operations and displays them in a structured, readable format.
"""

from dataclasses import dataclass, field
from pathlib import Path

from unpackr.utils.presentation import removal_verb, rule


@dataclass
class DryRunPlan:
    """Tracks planned operations for dry-run summary."""

    # Archive operations
    archives_to_extract: list[tuple[Path, int]] = field(
        default_factory=list[tuple[Path, int]]
    )  # (archive_path, size_bytes)
    archives_to_skip: list[tuple[Path, str]] = field(default_factory=list[tuple[Path, str]])  # (archive_path, reason)
    archives_to_remove: list[tuple[Path, str]] = field(default_factory=list[tuple[Path, str]])

    # Video operations
    videos_to_move: list[tuple[Path, int, str]] = field(
        default_factory=list[tuple[Path, int, str]]
    )  # (video_path, size_bytes, resolution)
    videos_to_skip: list[tuple[Path, str]] = field(default_factory=list[tuple[Path, str]])  # (video_path, reason)
    videos_to_delete: list[tuple[Path, str]] = field(default_factory=list[tuple[Path, str]])  # (sample_path, reason)
    videos_to_hold: list[tuple[Path, str]] = field(default_factory=list[tuple[Path, str]])  # still being written
    video_destinations: dict[str, str] = field(default_factory=dict[str, str])  # str(video) -> relative destination

    # Cleanup operations
    junk_files: list[Path] = field(default_factory=list[Path])
    folders_to_delete: list[Path] = field(default_factory=list[Path])
    folders_to_keep: list[tuple[Path, str]] = field(default_factory=list[tuple[Path, str]])  # (folder_path, reason)

    # PAR2 operations
    par2_to_process: list[tuple[Path, int]] = field(default_factory=list[tuple[Path, int]])  # (folder_path, file_count)

    def add_archive_extract(self, archive: Path, size_bytes: int) -> None:
        """Record archive extraction."""
        self.archives_to_extract.append((archive, size_bytes))

    def add_archive_skip(self, archive: Path, reason: str) -> None:
        """Record an archive left in place."""
        self.archives_to_skip.append((archive, reason))

    def add_archive_remove(self, archive: Path, reason: str) -> None:
        """Record a damaged set the live run would remove."""
        self.archives_to_remove.append((archive, reason))

    def add_video_move(self, video: Path, size_bytes: int, resolution: str = "unknown", destination: str = "") -> None:
        """Record video move (destination: final path relative to the destination folder)."""
        self.videos_to_move.append((video, size_bytes, resolution))
        if destination:
            self.video_destinations[str(video)] = destination

    def add_video_skip(self, video: Path, reason: str) -> None:
        """Record skipped video."""
        self.videos_to_skip.append((video, reason))

    def add_video_delete(self, video: Path, reason: str) -> None:
        """Record video deletion."""
        self.videos_to_delete.append((video, reason))

    def add_video_hold(self, video: Path, reason: str) -> None:
        """Record a video left in place because it is still being written."""
        self.videos_to_hold.append((video, reason))

    def add_junk_file(self, file: Path) -> None:
        """Record junk file."""
        self.junk_files.append(file)

    def add_folder_delete(self, folder: Path) -> None:
        """Record folder deletion."""
        self.folders_to_delete.append(folder)

    def add_folder_keep(self, folder: Path, reason: str) -> None:
        """Record folder preservation."""
        self.folders_to_keep.append((folder, reason))

    def add_par2_process(self, folder: Path, file_count: int) -> None:
        """Record PAR2 processing."""
        self.par2_to_process.append((folder, file_count))

    def format_size(self, size_bytes: int) -> str:
        """Format byte size in human-readable format."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def print_summary(self, delete_mode: str = "quarantine") -> None:
        """Print formatted dry-run summary. The removal verb follows delete_mode."""
        verb = removal_verb(delete_mode)
        line = rule()
        print("\n" + line)
        print("DRY RUN SUMMARY")
        print(line)

        # PAR2 Section
        if self.par2_to_process:
            total_files = sum(count for _, count in self.par2_to_process)
            print(f"\nPAR2 VERIFICATION/REPAIR ({len(self.par2_to_process)} folders, {total_files} files):")
            for folder, count in self.par2_to_process:
                print(f"  Process: {folder.name} ({count} PAR2 files)")

        # Archives Section
        if self.archives_to_extract or self.archives_to_skip or self.archives_to_remove:
            total_size = sum(size for _, size in self.archives_to_extract)
            print(f"\nARCHIVES ({len(self.archives_to_extract)} to extract, {self.format_size(total_size)}):")

            for archive, size in self.archives_to_extract:
                print(f"  Extract: {archive.name} ({self.format_size(size)})")

            if self.archives_to_remove:
                print(f"\n  DAMAGED, RE-DOWNLOAD ({len(self.archives_to_remove)}):")
                for archive, reason in self.archives_to_remove:
                    print(f"    {verb}: {archive.name} - {reason}")

            if self.archives_to_skip:
                print(f"\n  KEPT ({len(self.archives_to_skip)}):")
                for archive, reason in self.archives_to_skip:
                    print(f"    Keep: {archive.name} - {reason}")

        # Videos Section
        if self.videos_to_move or self.videos_to_skip or self.videos_to_delete or self.videos_to_hold:
            total_size = sum(size for _, size, _ in self.videos_to_move)
            print(f"\nVIDEOS ({len(self.videos_to_move)} to move, {self.format_size(total_size)}):")

            for video, size, resolution in self.videos_to_move:
                res_str = f", {resolution}" if resolution != "unknown" else ""
                print(f"  Move: {video.name} ({self.format_size(size)}{res_str}, validated during the live run)")
                if str(video) in self.video_destinations:
                    print(f"        -> {self.video_destinations[str(video)]}")

            if self.videos_to_delete:
                print(f"\n  {verb.upper()} SAMPLES ({len(self.videos_to_delete)}):")
                for video, reason in self.videos_to_delete:
                    print(f"    {verb}: {video.name} - {reason}")

            if self.videos_to_hold:
                print(f"\n  HOLD ({len(self.videos_to_hold)}):")
                for video, reason in self.videos_to_hold:
                    print(f"    Hold: {video.name} - {reason}")

            if self.videos_to_skip:
                print(f"\n  KEPT ({len(self.videos_to_skip)}):")
                for video, reason in self.videos_to_skip:
                    print(f"    Keep: {video.name} - {reason}")

        # Cleanup Section
        if self.junk_files or self.folders_to_delete or self.folders_to_keep:
            print("\nCLEANUP:")

            if self.junk_files:
                # Group by extension
                by_extension: dict[str, int] = {}
                for file in self.junk_files:
                    ext = file.suffix.lower()
                    by_extension[ext] = by_extension.get(ext, 0) + 1

                junk_summary = ", ".join(f"{count} {ext}" for ext, count in sorted(by_extension.items()))
                print(f"  {verb} {len(self.junk_files)} junk files ({junk_summary})")

            if self.folders_to_delete:
                print(f"  {verb} {len(self.folders_to_delete)} empty/junk folders")
                for folder in self.folders_to_delete[:5]:  # Show first 5
                    print(f"    - {folder.name}")
                if len(self.folders_to_delete) > 5:
                    print(f"    ... and {len(self.folders_to_delete) - 5} more")

            if self.folders_to_keep:
                print(f"\n  KEEP ({len(self.folders_to_keep)} folders protected):")
                for folder, reason in self.folders_to_keep:
                    print(f"    Keep: {folder.name} - {reason}")

        # Disk Space Summary
        archives_freed = sum(size for _, size in self.archives_to_extract)
        dest_used = sum(size for _, size, _ in self.videos_to_move)

        if archives_freed > 0 or dest_used > 0:
            print("\nDISK SPACE:")
            if archives_freed > 0:
                print(f"  Source freed: {self.format_size(archives_freed)} (after cleanup)")
            if dest_used > 0:
                print(f"  Destination used: {self.format_size(dest_used)}")

        # Summary counts
        print("\n" + rule("-"))
        print("SUMMARY:")
        print(
            f"  Archives: {len(self.archives_to_extract)} extract, "
            f"{len(self.archives_to_remove)} {verb.lower()}, {len(self.archives_to_skip)} kept"
        )
        print(
            f"  Videos: {len(self.videos_to_move)} move, {len(self.videos_to_delete)} {verb.lower()}, "
            f"{len(self.videos_to_hold)} hold, {len(self.videos_to_skip)} kept"
        )
        print(f"  Cleanup: {len(self.junk_files)} junk files, {len(self.folders_to_delete)} folders")
        print(f"  Protected: {len(self.folders_to_keep)} content folders kept")
        print(rule() + "\n")
