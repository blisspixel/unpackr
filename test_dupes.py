"""Quick test of duplicate detection."""
from pathlib import Path
from vhealth import VideoHealthChecker
from core import Config

config = Config()
checker = VideoHealthChecker(config)

# Get video files
path = Path("G:/out4")
video_files = checker._find_videos(path)

print(f"Found {len(video_files)} videos")
print("Detecting duplicates...")

# Run just the duplicate detection
checker._detect_duplicates(video_files)

print(f"\nConfirmed duplicates: {len(checker.duplicate_videos)}")
for video, original, reason in checker.duplicate_videos:
    print(f"  {video.name}")
    print(f"    -> {original.name}")
    print(f"    {reason}")

print(f"\nPotential duplicates: {len(checker.potential_duplicates)}")
for video1, video2, similarity in checker.potential_duplicates[:5]:  # Show first 5
    print(f"  {video1.name}")
    print(f"  {video2.name}")
    print(f"    Similarity: {similarity:.0%}")
