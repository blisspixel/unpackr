import os
import shutil
import logging
from logging.handlers import RotatingFileHandler
import argparse
import sys
import re
from tqdm import tqdm
import time
import psutil
from pathlib import Path
import subprocess
import tempfile
from colorama import init, Fore, Style

# Constants
LOGS_FOLDER = Path('logs')
LOG_FILE = LOGS_FOLDER / 'app.log'
VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.mpg', '.mpeg', '.m4v', '.3gp', '.webm']

# Ensure the logs directory exists
os.makedirs(LOGS_FOLDER, exist_ok=True)

# Set up logging with RotatingFileHandler
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
log_handler = RotatingFileHandler(LOG_FILE, maxBytes=1048576, backupCount=10)
log_handler.setFormatter(log_formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

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

def log_subprocess_error(error, process_name):
    """
    Logs detailed error information for a CalledProcessError exception.
    """
    logging.error(f"{process_name} failed with return code {error.returncode}")
    logging.error(f"Command: {error.cmd}")
    if error.output:
        logging.error(f"Output:\n{error.output}")
    logging.error("Traceback:\n" + traceback.format_exc())

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

def contains_unwanted_files(folder: Path) -> bool:
    """
    Checks if the folder contains files other than video, PAR2, RAR, and allowable non-video files.
    """
    for file in folder.rglob('*'):
        if file.is_file() and not (
            file.suffix.lower() in VIDEO_EXTENSIONS or
            file.suffix.lower() == '.par2' or
            file.suffix.lower() == '.rar'
        ):
            return True
    return False

def process_par2_files(folder: Path) -> bool:
    try:
        process = subprocess.Popen(['par2', 'r', str(folder / '*.par2')],
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   text=True,
                                   encoding='utf-8',
                                   errors='replace')
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            logging.error(f"PAR2 processing error for {folder}:\nStdout: {stdout}\nStderr: {stderr}")
            return False  # Indicate a PAR2 processing error occurred
        return True
    except Exception as e:
        logging.error(f"Unexpected error during PAR2 processing for {folder}: {e}")
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
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                logging.error(f"RAR extraction error for {folder}:\nStdout: {stdout}\nStderr: {stderr}")
                return False
        return True
    except Exception as e:
        logging.error(f"Unexpected error during RAR extraction for {folder}: {e}")
        return False

def wait_for_file_release(file_path, max_attempts=10, delay=1):
    for attempt in range(max_attempts):
        is_locked = False
        for proc in psutil.process_iter(attrs=['pid', 'name']):
            try:
                if file_path in (f.path for f in proc.open_files()):
                    is_locked = True
                    break
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue  # Ignore processes that cannot be accessed

        if not is_locked:
            return True

        time.sleep(delay)  # Wait before retrying

    return False

def safe_delete_folder(folder: Path):
    """
    Attempts to safely delete a folder, handling any exceptions.
    """
    try:
        shutil.rmtree(folder)
        logging.info(f"Successfully deleted folder {folder}")
    except Exception as e:
        logging.error(f"Failed to delete folder {folder} on first attempt: {e}")
        time.sleep(5)  # Wait for a short period before trying again
        try:
            shutil.rmtree(folder)
            logging.info(f"Successfully deleted folder {folder} on second attempt")
        except Exception as e:
            logging.error(f"Repeated error deleting folder {folder}: {e}")

def check_video_health(video_file: Path) -> bool:
    try:
        # Create a temporary file
        with tempfile.TemporaryFile(mode='w+') as temp_output:
            result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video_file), '-f', 'null', '-'],
                                    stdout=temp_output, stderr=temp_output, text=True)

            # Check if ffmpeg found errors
            temp_output.seek(0)  # Go to the start of the file to read content
            output = temp_output.read()
            if result.returncode != 0:
                logging.error(f"Corrupt video file detected: {video_file}\n{output}")
                return False
            return True
    except FileNotFoundError:
        logging.warning("FFMPEG is not installed. Skipping health check.")
        return True
    except Exception as e:
        logging.error(f"Error during FFMPEG health check: {e}")
        return False

def is_file_in_use(file_path: Path) -> bool:
    """
    Checks if the file is currently in use by any process.
    """
    for proc in psutil.process_iter():
        try:
            for item in proc.open_files():
                if file_path == Path(item.path):
                    return True
        except Exception:
            continue
    return False

def delete_video_file_with_retry(file_path, max_attempts=5):
    for attempt in range(max_attempts):
        try:
            # Try to open the file in exclusive mode
            with open(file_path, 'a+') as f:
                pass
            # If successful, delete the file
            os.remove(file_path)
            logging.info(f"Successfully deleted video file: {file_path}")
            return True
        except PermissionError:
            logging.error(f"Attempt {attempt + 1} - Error deleting video file {file_path}: Access is denied")
        except FileNotFoundError:
            logging.error(f"Attempt {attempt + 1} - Error deleting video file {file_path}: File not found")
        except Exception as e:
            logging.error(f"Attempt {attempt + 1} - Error deleting video file {file_path}: {e}")
        time.sleep(1)  # Wait before retrying
    logging.error(f"Failed to delete video file {file_path} after {max_attempts} attempts.")
    return False

def update_progress_bar(pbar, description):
    """
    Updates the progress bar with a custom description.
    """
    pbar.set_description(description)
    pbar.refresh()  # Refresh the progress bar to show the updated description immediately

def is_folder_empty_or_removable(folder: Path, par2_error: bool, rar_error: bool) -> bool:
    """
    Checks if the folder is empty or contains only files that can be removed.
    This includes checking for errors in PAR2 and RAR processing.
    """
    removable_extensions = ['.sfv', '.nfo', '.sfv', '.srr', '.srs', '.url', '.db', '.nzb', '.txt']
    jpg_count = 0

    for file in folder.iterdir():
        if file.is_dir():
            logging.info(f"Folder '{folder}' not deleted: contains subdirectory '{file.name}'")
            return False

        file_ext = file.suffix.lower()
        if file_ext == '.jpg':
            jpg_count += 1
            if jpg_count > 1:
                logging.info(f"Folder '{folder}' not deleted: contains more than one JPG file '{file.name}'")
                return False
        elif file_ext in removable_extensions or (file_ext.startswith('.r') and file_ext[2:].isdigit()):
            continue
        elif (file_ext == '.par2' and par2_error) or (file_ext == '.rar' and rar_error):
            continue  # Treat PAR2 or RAR files as removable if there were processing errors
        else:
            logging.info(f"Folder '{folder}' not deleted: contains non-removable file '{file.name}'")
            return False

    # If a PAR2 or RAR error occurred and only removable files are present, the folder can be deleted
    return True if jpg_count <= 1 else False

def is_shortcut(file: Path) -> bool:
    """
    Checks if a file is a shortcut (e.g., .lnk in Windows).
    """
    return file.suffix.lower() in ['.lnk', '.url']  # Add other shortcut types if needed

def terminate_related_processes(file_name, allowed_processes=['ffmpeg', '7z']):
    """
    Terminates processes that might be using the file.
    """
    for process in psutil.process_iter():
        try:
            process_info = process.as_dict(attrs=['pid', 'name'])
            if process_info['name'] in allowed_processes and file_name in process.cmdline():
                process.terminate()
                logging.info(f"Terminated process {process_info['name']} (PID: {process_info['pid']}) that was using file {file_name}")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

def process_subfolder(subfolder: Path, destination_dir: Path, pbar):
    """
    Recursive function to process each subfolder.
    """
    for sub in subfolder.iterdir():
        if sub.is_dir():
            process_subfolder(sub, destination_dir, pbar)  # Recursive call for deeper subfolders
        else:
            process_file(sub, destination_dir, pbar)

    # Check if the subfolder can be deleted after processing its contents
    if is_folder_empty_or_removable(subfolder, False, False):  # Assuming no PAR2 or RAR files in subfolders
        safe_delete_folder(subfolder)
        logging.info(f"Deleted subfolder after processing: {subfolder}")

def process_file(file: Path, destination_dir: Path, pbar):
    """
    Processes individual files within folders and subfolders.
    """
    if file.suffix.lower() in VIDEO_EXTENSIONS:
        if check_video_health(file):
            try:
                destination_file = destination_dir / file.name
                shutil.move(str(file), str(destination_file))
                logging.info(f"Video file verified and moved: {destination_file}")
            except Exception as e:
                logging.error(f"Error moving file {file}: {e}")
        else:
            try:
                file.unlink(missing_ok=True)
                logging.error(f"Corrupt video file detected and deleted: {file}")
            except Exception as e:
                logging.error(f"Error deleting corrupt video file {file}: {e}")
    elif file.suffix.lower() in ['.jpg'] and len(list(file.parent.glob('*.jpg'))) == 1:  # Single JPG file in folder
        try:
            file.unlink(missing_ok=True)
            logging.info(f"Deleted single JPG file: {file}")
        except Exception as e:
            logging.error(f"Error deleting JPG file {file}: {e}")

def delete_video_file_with_retry(video_file: Path, max_attempts: int = 5, retry_delay_seconds: int = 1):
    for attempt in range(max_attempts):
        terminate_related_processes(str(video_file))
        try:
            # Wait before retrying deletion
            if attempt > 0:
                time.sleep(retry_delay_seconds)

            video_file.unlink(missing_ok=True)
            logging.info(f"Successfully deleted video file: {video_file}")
            return True
        except Exception as e:
            logging.error(f"Attempt {attempt + 1} - Error deleting video file {video_file}: {e}")

    logging.error(f"Failed to delete video file {video_file} after {max_attempts} attempts.")
    return False

def process_folder(folder: Path, destination_dir: Path, pbar):
    """
    Processes the given folder for video, PAR2, and RAR files.
    Moves video files to a specified destination and cleans up the folder.
    Performs a health check on video files using FFMPEG.
    """
    update_progress_bar(pbar, f"Starting processing for {folder.name}")

    initial_video_files = find_video_files(folder)
    processed_files = set()  # Track processed files
    par2_error, rar_error = False, False

    # Process initial video files
    for video_file in initial_video_files:
        update_progress_bar(pbar, f"Checking health of video file {video_file.name}")
        if check_video_health(video_file):
            try:
                destination_file = destination_dir / video_file.name
                shutil.move(str(video_file), str(destination_file))
                logging.info(f"Video file verified and moved: {destination_file}")
                processed_files.add(video_file)  # Mark as processed
            except Exception as e:
                logging.error(f"Error moving file {video_file}: {e}")
        else:
            # Before attempting to delete the file, wait for it to be released
            if wait_for_file_release(str(video_file)):
                success = delete_video_file_with_retry(video_file)
                if success:
                    processed_files.add(video_file)  # Mark as processed
            else:
                logging.error(f"Timeout waiting for file release: {video_file}")

    # Process PAR2 files if they exist
    if any(file.suffix == '.par2' for file in folder.iterdir()):
        update_progress_bar(pbar, f"Repairing PAR2 files in {folder.name}")
        par2_error = not process_par2_files(folder)

    # Process RAR files if they exist
    if any(file.suffix == '.rar' for file in folder.iterdir()):
        update_progress_bar(pbar, f"Extracting RAR files in {folder.name}")
        rar_error = not process_rar_files(folder)

    # Process each subfolder
    for subfolder in folder.iterdir():
        if subfolder.is_dir():
            process_subfolder(subfolder, destination_dir, pbar)

    # Recheck for video files that might have been extracted
    post_process_video_files = find_video_files(folder)
    for video_file in post_process_video_files:
        if video_file not in processed_files:  # Skip already processed files
            update_progress_bar(pbar, f"Verifying extracted video file {video_file.name}")
            if check_video_health(video_file):
                try:
                    destination_file = destination_dir / video_file.name
                    shutil.move(str(video_file), str(destination_file))
                    logging.info(f"Video file verified and moved: {destination_file}")
                except Exception as e:
                    logging.error(f"Error moving file {video_file}: {e}")
            else:
                if wait_for_file_release(str(video_file)):
                    delete_video_file_with_retry(video_file)

    # Final folder check
    update_progress_bar(pbar, f"Finalizing folder {folder.name}")
    if is_folder_empty_or_removable(folder, par2_error, rar_error):
        safe_delete_folder(folder)
        logging.info(f"Deleted folder after processing: {folder}")
    else:
        logging.info(f"Folder not deleted: {folder} (contains non-removable files or not empty)")

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
    print(Fore.YELLOW + " - Scan for videos, check their health with ffmpeg." + Style.RESET_ALL)
    print(Fore.YELLOW + " - Scan for PAR2 and RAR files." + Style.RESET_ALL)
    print(Fore.YELLOW + " - Move healthy video files to: " + str(destination_dir) + Style.RESET_ALL)
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
    folders_with_unwanted_files = 0

    with tqdm(total=len(folders), unit="folder") as pbar:
        for folder in folders:
            video_files_before = len(find_video_files(folder))
            if video_files_before == 0:
                blank_folders += 1

            if contains_unwanted_files(folder):
                folders_with_unwanted_files += 1

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
    print(f"Folders with unwanted files: {folders_with_unwanted_files}")

if __name__ == '__main__':
    main()
