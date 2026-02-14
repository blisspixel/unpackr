"""
Pre-flight check for test run
Analyzes G:\test to predict what will happen
"""

from pathlib import Path
from colorama import init, Fore, Style

init()

def analyze_test_folder():
    """Analyze test folder and predict outcomes."""
    test_dir = Path("G:/test")
    
    if not test_dir.exists():
        print(f"{Fore.RED}Test directory does not exist: {test_dir}{Style.RESET_ALL}")
        return
    
    print(f"{Fore.CYAN}Pre-Flight Analysis: G:\\test{Style.RESET_ALL}")
    print("="*60)
    
    folders = [f for f in test_dir.iterdir() if f.is_dir()]
    files = [f for f in test_dir.iterdir() if f.is_file()]
    
    print(f"\nFound {len(folders)} folders and {len(files)} files")
    
    # Analyze folders
    print(f"\n{Fore.YELLOW}Folders:{Style.RESET_ALL}")
    video_folders = []
    content_folders = []
    
    for folder in sorted(folders):
        folder_files = list(folder.iterdir())
        video_files = [f for f in folder_files if f.suffix.lower() in ['.mp4', '.mov', '.avi', '.mkv']]
        rar_files = [f for f in folder_files if f.suffix.lower() in ['.rar'] or (f.suffix.startswith('.r') and f.suffix[2:].isdigit())]
        par2_files = [f for f in folder_files if f.suffix.lower() == '.par2']
        mp3_files = [f for f in folder_files if f.suffix.lower() == '.mp3']
        doc_files = [f for f in folder_files if f.suffix.lower() in ['.pdf', '.docx', '.doc']]
        image_files = [f for f in folder_files if f.suffix.lower() in ['.jpg', '.png', '.webp', '.jpeg']]
        
        if video_files or rar_files:
            video_folders.append(folder.name)
            print(f"  {Fore.GREEN}[VIDEO]{Style.RESET_ALL} {folder.name}")
            if video_files:
                print(f"          {len(video_files)} video(s)")
            if rar_files:
                print(f"          {len(rar_files)} RAR file(s) - will extract")
            if par2_files:
                print(f"          {len(par2_files)} PAR2 file(s) - will repair")
        elif mp3_files or doc_files or (len(image_files) >= 2):
            content_folders.append(folder.name)
            print(f"  {Fore.BLUE}[KEEP]{Style.RESET_ALL}  {folder.name}")
            if mp3_files:
                print(f"          {len(mp3_files)} music file(s)")
            if doc_files:
                print(f"          {len(doc_files)} document(s)")
            if image_files:
                print(f"          {len(image_files)} image(s)")
    
    # Analyze files
    print(f"\n{Fore.YELLOW}Files in root:{Style.RESET_ALL}")
    for file in sorted(files):
        if file.suffix.lower() in ['.mp4', '.mov', '.avi', '.mkv']:
            print(f"  {Fore.GREEN}[VIDEO]{Style.RESET_ALL} {file.name}")
        else:
            print(f"  {Fore.YELLOW}[OTHER]{Style.RESET_ALL} {file.name}")
    
    # Predictions
    print(f"\n{Fore.CYAN}Predictions:{Style.RESET_ALL}")
    print(f"  Video folders to process: {Fore.GREEN}{len(video_folders)}{Style.RESET_ALL}")
    print(f"  Content folders to keep: {Fore.BLUE}{len(content_folders)}{Style.RESET_ALL}")
    print(f"  Videos in root: {Fore.GREEN}{len([f for f in files if f.suffix.lower() in ['.mp4', '.mov']])}{Style.RESET_ALL}")
    
    print(f"\n{Fore.YELLOW}Expected actions:{Style.RESET_ALL}")
    print("  1. Extract RAR archives (if any)")
    print("  2. Repair videos with PAR2")
    print("  3. Validate video health")
    print("  4. Move healthy videos to destination")
    print("  5. Delete video folders")
    print(f"  6. Keep content folders: {', '.join(content_folders)}")
    
    print(f"\n{Fore.GREEN}Ready to proceed with test run!{Style.RESET_ALL}")
    print("\nCommand to run:")
    print('  python unpackr.py --source "G:\\test" --destination "G:\\test_output"')

if __name__ == '__main__':
    analyze_test_folder()
