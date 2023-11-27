import os
import shutil
import logging
import argparse
import sys
from tqdm import tqdm
import time
from pathlib import Path
import subprocess
from colorama import init, Fore, Style

# Constants
LOG_FILE = Path('app.log')
VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.mpg', '.mpeg', '.m4v', '.3gp', '.webm']

# Set up logging
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

init()

# ASCII Art
ascii_art = r"""
                               _         
  _   _ _ __  _ __   __ _  ___| | ___ __ 
 | | | | '_ \| '_ \ / _` |/ __| |/ / '__|
 | |_| | | | | |_) | (_| | (__|   <| |   
  \__,_|_| |_| .__/ \__,_|\___|_|\_\_|   
             |_|        

"""

def get_user_input(prompt: str) -> Path:
    """
    Prompts the user for a directory path and returns a Path object.
    Ensures that the provided path is a valid directory.
    """
    while True:
        user_input = input(prompt).strip()
        if os.path.isdir(user_input):
            return Path(user_input)
        else:
            print("Invalid path. Please enter a valid directory path.")

def confirm_action() -> bool:
    """
    Asks the user for confirmation to proceed with the action.
    Ensures that the user is aware that this process will manipulate files and folders.
    """
    prompt = (
        "WARNING: This process will search the specified directory for video, PAR2, and RAR files. "
        "It will move video files to a destination folder, repair files using PAR2, extract RAR archives, "
        "and delete folders that have been processed. This action cannot be undone. "
        "Type 'y' or 'yes' to confirm and proceed, or any other key to cancel: "
    )
    confirmation = input(prompt).strip().lower()
    return confirmation in ['y', 'yes']

def count_all_files(folder: Path) -> int:
    """
    Counts all files in the given folder.
    """
    return len([file for file in folder.rglob('*') if file.is_file()])

def find_video_files(folder: Path) -> list:
    """
    Recursively finds video files in the given folder.
    Returns a list of paths to video files.
    """
    video_files = [file for file in folder.rglob('*') if file.suffix.lower() in VIDEO_EXTENSIONS]
    return video_files

def contains_non_video_files(folder: Path) -> bool:
    """
    Checks if the folder contains files other than the specified video files.
    """
    all_files = [file for file in folder.rglob('*') if file.is_file()]
    non_video_files = [file for file in all_files if file.suffix.lower() not in VIDEO_EXTENSIONS]
    return len(non_video_files) > 0

def process_par2_files(folder: Path) -> bool:
    try:
        process = subprocess.run(['par2', 'r', str(folder / '*.par2')], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for line in process.stdout.splitlines():
            print(line)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"PAR2 processing error for {folder}: {e}")
        return False

def process_rar_files(folder: Path) -> bool:
    try:
        for file in folder.glob('*.rar'):
            process = subprocess.Popen(['7z', 'x', str(file), f'-o{folder}', '-aoa'], 
                                       stdout=subprocess.PIPE, 
                                       stderr=subprocess.PIPE, 
                                       text=True, 
                                       encoding='utf-8', 
                                       errors='replace')
            if process.stdout:
                for line in iter(process.stdout.readline, ''):
                    print(line, end='')
            process.wait()
            if process.returncode != 0:
                logging.error(f"RAR extraction error for {folder}")
                return False
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"RAR extraction error for {folder}: {e}")
        return False

def safe_delete_folder(folder: Path):
    """
    Attempts to safely delete a folder, handling any exceptions.
    """
    try:
        shutil.rmtree(folder)
    except Exception as e:
        logging.error(f"Error deleting folder {folder}: {e}")
        time.sleep(5)  # Wait for a short period before trying again
        try:
            shutil.rmtree(folder)
        except Exception as e:
            logging.error(f"Repeated error deleting folder {folder}: {e}")

def check_video_health(video_file: Path) -> bool:
    """
    Checks the health of a video file using ffmpeg.
    Returns True if the video is healthy, False if corrupt.
    """
    try:
        result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video_file), '-f', 'null', '-'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0 or result.stderr:
            logging.error(f"Corrupt video file detected: {video_file}\n{result.stderr}")
            return False
        return True
    except FileNotFoundError:
        logging.warning("FFMPEG is not installed. Skipping health check.")
        return True
    except Exception as e:
        logging.error(f"Error during FFMPEG health check: {e}")
        return True

def update_progress_bar(pbar, description):
    """
    Updates the progress bar with a custom description.
    """
    pbar.set_description(description)
    pbar.refresh()  # Refresh the progress bar to show the updated description immediately

def process_folder(folder: Path, destination_dir: Path, pbar):
    """
    Processes the given folder for video, PAR2, and RAR files.
    Moves video files to a specified destination and cleans up the folder.
    Performs a health check on video files using FFMPEG.
    """
    update_progress_bar(pbar, f"Starting processing for {folder.name}")

    initial_video_files = find_video_files(folder)
    if initial_video_files:
        update_progress_bar(pbar, f"Moving video files from {folder.name}")
        for video_file in initial_video_files:
            try:
                destination_file = destination_dir / video_file.name
                shutil.move(str(video_file), str(destination_file))
                update_progress_bar(pbar, f"Checking health of video file {video_file.name}")
                if not check_video_health(destination_file):
                    destination_file.unlink(missing_ok=True)
                    logging.error(f"Corrupt video file detected and deleted: {destination_file}")
                else:
                    logging.info(f"Video file verified and moved: {destination_file}")
            except Exception as e:
                logging.error(f"Error moving file {video_file}: {e}")
        update_progress_bar(pbar, f"Finished moving video files from {folder.name}")
        safe_delete_folder(folder)
        logging.info(f"Moved video file(s) and deleted folder: {folder}")
        return

    has_par2 = any(file.suffix == '.par2' for file in folder.iterdir())
    if has_par2:
        update_progress_bar(pbar, f"Repairing PAR2 files in {folder.name}")
        process_par2_files(folder)
        update_progress_bar(pbar, f"Finished repairing PAR2 files in {folder.name}")

    has_rar = any(file.suffix == '.rar' for file in folder.iterdir())
    if has_rar:
        update_progress_bar(pbar, f"Extracting RAR files in {folder.name}")
        process_rar_files(folder)
        update_progress_bar(pbar, f"Finished extracting RAR files in {folder.name}")

    post_process_video_files = find_video_files(folder)
    if post_process_video_files:
        update_progress_bar(pbar, f"Moving extracted video files from {folder.name}")
        for video_file in post_process_video_files:
            try:
                destination_file = destination_dir / video_file.name
                shutil.move(str(video_file), str(destination_file))
                if not check_video_health(destination_file):
                    destination_file.unlink(missing_ok=True)
                    logging.error(f"Corrupt video file detected and deleted: {destination_file}")
                else:
                    logging.info(f"Video file verified and moved: {destination_file}")
            except Exception as e:
                logging.error(f"Error moving file {video_file}: {e}")
        update_progress_bar(pbar, f"Finished moving extracted video files from {folder.name}")
        safe_delete_folder(folder)
        logging.info(f"Moved extracted video file(s) and deleted folder: {folder}")
    else:
        logging.info(f"No video files found after processing, folder not deleted: {folder}")

    update_progress_bar(pbar, f"Finished processing {folder.name}")

def main():
    print(Fore.YELLOW + ascii_art + Style.RESET_ALL)

    parser = argparse.ArgumentParser(description="Automated video file processing script.")
    parser.add_argument('--source', help='Path to the source downloads directory.', required=False)
    parser.add_argument('--destination', help='Path to the destination directory.', required=False)
    args = parser.parse_args()

    if args.source and args.destination:
        download_dir = Path(args.source)
        destination_dir = Path(args.destination)
        if not download_dir.is_dir() or not destination_dir.is_dir():
            print(Fore.RED + "Invalid source or destination path. Please enter valid directory paths." + Style.RESET_ALL)
            sys.exit(1)
    else:
        print(Style.BRIGHT + Fore.YELLOW + "This script requires 'par2cmdline' (par2.exe) in the script directory and 7-Zip installed and available in PATH." + Style.RESET_ALL)
        download_dir = get_user_input("Enter the path to your downloads directory: ")
        destination_dir = get_user_input("Enter the path to your destination directory: ")

    print(Style.BRIGHT + Fore.RED + "IMPORTANT WARNING:" + Style.RESET_ALL)
    print(f"The process will scan the directory: {Fore.CYAN}{download_dir}{Style.RESET_ALL}")
    print("Actions to be performed:")
    print(Fore.YELLOW + " - Scan for video, PAR2, and RAR files." + Style.RESET_ALL)
    print(Fore.YELLOW + " - Move video files to: " + str(destination_dir) + Style.RESET_ALL)
    print(Fore.YELLOW + " - Repair files using PAR2 and extract RAR archives." + Style.RESET_ALL)
    print(Fore.YELLOW + " - Delete folders that have been processed." + Style.RESET_ALL)
    print("This action is irreversible and may lead to data loss. Ensure you have backups if necessary.")
    print("All actions will be logged to: " + str(LOG_FILE))
    print("\nProcessing will automatically start in 10 seconds. To cancel, press Ctrl+C now.")

    try:
        for i in range(10, 0, -1):
            sys.stdout.write(f"\r{Fore.GREEN}Starting in {i} seconds... (Press Ctrl+C to cancel) {Style.RESET_ALL}")
            sys.stdout.flush()
            time.sleep(1)
    except KeyboardInterrupt:
        print(Fore.RED + "\nOperation cancelled by user." + Style.RESET_ALL)
        sys.exit(1)

    print(Fore.GREEN + "\nStarting processing..." + Style.RESET_ALL)

    folders = [folder for folder in download_dir.iterdir() if folder.is_dir()]
    total_video_files_moved = 0
    total_folders_deleted = 0
    blank_folders = 0
    folders_with_non_video_files = 0

    with tqdm(total=len(folders), unit="folder") as pbar:
        for folder in folders:
            video_files_before = len(find_video_files(folder))
            if video_files_before == 0:
                blank_folders += 1

            process_folder(folder, destination_dir, pbar)

            if folder.exists() and contains_non_video_files(folder):
                folders_with_non_video_files += 1

            total_video_files_moved += video_files_before
            if not folder.exists():
                total_folders_deleted += 1

            pbar.update(1)

    print(Fore.GREEN + "\nProcessing complete." + Style.RESET_ALL)
    print(f"Total folders processed: {len(folders)}")
    print(f"Total video files moved: {total_video_files_moved}")
    print(f"Total folders deleted: {total_folders_deleted}")
    print(f"Blank folders: {blank_folders}")
    print(f"Folders with non-video files: {folders_with_non_video_files}")

if __name__ == '__main__':
    main()