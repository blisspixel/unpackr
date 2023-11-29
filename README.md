Unpackr: Your Digital Declutterer - Automate, Organize, and Streamline Your Downloads with Ease

Work in progress

## Concept

Problem: Imagine your download folder cluttered with numerous legally acquired files. Within this digital maze, you find not just the video files you desire but also a myriad of subfolders, irrelevant files, and complicated file formats like PAR and RAR. Navigating through this chaos to extract, repair, and organize the content you actually need can be overwhelming, consuming your valuable time and energy.

Solution: Unpackr is a specialized tool for cleaning up your download folder, with a focus on video files. It automates the tedious tasks associated with handling a variety of file types and structures. By efficiently managing RAR file extraction, repairing files with PAR2, and relocating video files to a designated destination, Unpackr turns a complex process into a seamless experience. Importantly, it also ensures the integrity of your video files by performing health checks using FFMPEG to detect any corruption, automatically deleting any corrupt files to maintain the quality of your collection.

The script is intelligently designed to sift through the clutter, distinguishing video files from other content. It respects and leaves untouched folders containing only non-video files, such as images or audio, allowing you to enjoy your legally acquired content without the hassle of manual organization.

## Disclaimer

Use Unpackr at your own risk. While it's designed to automate and simplify file management, it's important to understand that any form of automated file handling carries inherent risks, such as accidental deletion or misplacement of files. Always ensure that you have backups of important data and review the script's actions closely. The developers are not responsible for any loss of data or damage resulting from the use of this script.

## Features

- Scans directories for video files and RAR archives.
- Extracts RAR files using 7-Zip.
- Repairs files with PAR2.
- Moves processed video files to a specified destination.
- Uses FFMPEG to perform health checks on video files, deleting any that are found to be corrupt.
- Deletes folders after processing.
- Displays progress using a dynamic progress bar (with tqdm).
- Provides detailed statistics on the processing, including the number of video files moved, folders deleted, and blank or non-video file containing folders.

## Requirements

- Python 3.x
- [7-Zip](https://www.7-zip.org/)
- [par2cmdline](https://github.com/Parchive/par2cmdline)
- [FFMPEG](https://ffmpeg.org/download.html) (used for video file health checks)
- tqdm (Python package, installable via `pip install tqdm`)

## Setup

1. Clone the repository or download the script.
2. Ensure Python 3.x is installed on your system.
3. Install the required Python dependency:
pip install tqdm
4. Make sure 7-Zip, par2cmdline, and FFMPEG are installed and available in the system PATH.

## Usage

Run the script from the command line:
python unpacker.py

Follow the on-screen prompts to enter the path to your downloads directory and the destination directory for processed video files.

OR 

Run the script with command-line arguments:
python ./unpackr.py --source "G:\Test" --destination "G:\Test Out"
The script will process each folder, moving video files to the destination directory and deleting folders after processing. A progress bar will indicate the processing status, and upon completion, the script will display a summary of its actions.

## License

This project is licensed under the MIT License.
