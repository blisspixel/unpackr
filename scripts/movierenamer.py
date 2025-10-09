import os
import re
import csv
import datetime
import colorama
from colorama import Fore, Style

# ASCII Art and initialization
ascii_art = r"""
                    .__                                                            
  _____   _______  _|__| ____   _______   ____   ____ _____    _____   ___________ 
 /     \ /  _ \  \/ /  |/ __ \  \_  __ \_/ __ \ /    \\__  \  /     \_/ __ \_  __ \
|  Y Y  (  <_> )   /|  \  ___/   |  | \/\  ___/|   |  \/ __ \|  Y Y  \  ___/|  | \/
|__|_|  /\____/ \_/ |__|\___  >  |__|    \___  >___|  (____  /__|_|  /\___  >__|   
      \/                    \/               \/     \/     \/      \/     \/       
"""
colorama.init()

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def create_preview(folder_path, pattern):
    preview_data = []
    for filename in os.listdir(folder_path):
        match = pattern.match(filename)
        if match:
            new_name = match.group(1).replace('.', ' ') + '.' + match.group(2)
            preview_data.append((filename, new_name))
    return preview_data

def write_preview_to_csv(preview_data, folder_path):
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    preview_file = f'preview_{timestamp}.csv'
    with open(os.path.join(folder_path, preview_file), 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Original Name', 'New Name'])
        writer.writerows(preview_data)
    return preview_file

def rename_files(folder_path, pattern, undo_log):
    for filename in os.listdir(folder_path):
        match = pattern.match(filename)
        if match:
            new_name = match.group(1).replace('.', ' ') + '.' + match.group(2)
            try:
                os.rename(os.path.join(folder_path, filename), os.path.join(folder_path, new_name))
                undo_log.append((os.path.join(folder_path, new_name), os.path.join(folder_path, filename)))
                print(Fore.GREEN + f"Renamed '{filename}' to '{new_name}'" + Style.RESET_ALL)
            except Exception as e:
                print(Fore.RED + f"Error renaming '{filename}': {e}" + Style.RESET_ALL)

def undo_renaming(folder_path, undo_file):
    with open(os.path.join(folder_path, undo_file), newline='', encoding='utf-8') as file:
        reader = csv.reader(file)
        next(reader)  # Skip header
        for row in reader:
            try:
                os.rename(row[0], row[1])
                print(Fore.GREEN + f"Reverted '{row[0]}' to '{row[1]}'" + Style.RESET_ALL)
            except Exception as e:
                print(Fore.RED + f"Error reverting '{row[0]}': {e}" + Style.RESET_ALL)

def find_undo_file(folder_path):
    for filename in os.listdir(folder_path):
        if filename.startswith("undo_log_") and filename.endswith(".csv"):
            return filename
    return None

def main():
    clear_screen()
    print(ascii_art)
    print(Fore.YELLOW + "This script will rename video files in a specified folder." + Style.RESET_ALL)
    print(Fore.RED + "WARNING: This process is irreversible. Please ensure you have backups of your files before proceeding." + Style.RESET_ALL)

    folder_path = input("Enter the full path of the folder containing the video files: ")
    if not (os.path.exists(folder_path) and os.path.isdir(folder_path)):
        print(Fore.RED + "The specified folder does not exist. Please check the path and try again." + Style.RESET_ALL)
        return

    undo_file = find_undo_file(folder_path)
    if undo_file:
        response = input(f"Undo file '{undo_file}' found. Do you want to revert the previous renaming? (yes/no): ")
        if response.lower() in ['yes', 'y']:
            undo_renaming(folder_path, undo_file)
            return

    pattern = re.compile(r"(.*?)\.\d{4}(?:\..*?)?\.(mp4|mkv|avi|mov)")
    preview_data = create_preview(folder_path, pattern)
    if not preview_data:
        print(Fore.BLUE + "No files to rename. Exiting." + Style.RESET_ALL)
        return

    preview_file = write_preview_to_csv(preview_data, folder_path)
    print(Fore.CYAN + f"Preview of proposed changes written to '{preview_file}'." + Style.RESET_ALL)
    response = input("Do you want to proceed with renaming? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print(Fore.MAGENTA + "Renaming cancelled." + Style.RESET_ALL)
        return

    undo_log = []
    rename_files(folder_path, pattern, undo_log)

    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    undo_file = f'undo_log_{timestamp}.csv'
    with open(os.path.join(folder_path, undo_file), 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['New Name', 'Original Name'])
        writer.writerows(undo_log)
    print(Fore.GREEN + f"Undo log written to '{undo_file}'. To undo the renaming, reverse the entries in this file by rerunning the script with the undo log file left in that location." + Style.RESET_ALL)

if __name__ == "__main__":
    main()
