import os
import shutil
from pathlib import Path

def setup_base_folders(base_dir):
    """Creates and returns the paths for the standard application folders."""
    input_dir = os.path.join(base_dir, "input")
    output_dir = os.path.join(base_dir, "output")
    folders = {
        "input": input_dir,
        "output": output_dir,
        "archive": os.path.join(input_dir, "archive"),
        "logs": os.path.join(output_dir, "logs")
    }
    for path in folders.values():
        os.makedirs(path, exist_ok=True)
    return folders

def get_cache_folders(base_dir):
    """Returns a dictionary of cache folder paths."""
    cache_dir = os.path.join(base_dir, "Cache")
    return {
        "cache_dir": cache_dir,
        "images_folder": os.path.join(cache_dir, "Images"),
        "pdf_folder": os.path.join(cache_dir, "FinalPDF"),
        "plotted_folder": os.path.join(cache_dir, "Ploted"),
        "excel_output_folder": os.path.join(cache_dir, "Excel"),
        "json_output_folder": os.path.join(cache_dir, "Json"),
        "digital_excel_folder": os.path.join(cache_dir, "DigitalExcel"),
        "merged_excel_folder": os.path.join(cache_dir, "MergedExcel")
    }

def create_cache_folders(base_dir):
    """Creates cache folders at runtime and returns their paths."""
    folders = get_cache_folders(base_dir)
    for path in folders.values():
        os.makedirs(path, exist_ok=True)
    return folders

def delete_cache_folder(base_dir):
    """Deletes cache folders upon completion or to ensure a fresh start."""
    cache_dir = os.path.join(base_dir, "Cache")
    if os.path.exists(cache_dir):
        try:
            shutil.rmtree(cache_dir)
        except Exception as e:
            print(f"Failed to delete cache folder: {e}")

def get_input_files(input_dir) -> list:
    """Returns a list of all files in the input folder (excluding subdirectories like archive)."""
    files = []
    if os.path.exists(input_dir):
        for f in os.listdir(input_dir):
            full_path = os.path.join(input_dir, f)
            if os.path.isfile(full_path):
                files.append(full_path)
    return files

def move_to_archive(file_path, archive_dir):
    """Moves a file to the archive folder."""
    if not os.path.exists(file_path):
        return
    
    os.makedirs(archive_dir, exist_ok=True)
    file_name = os.path.basename(file_path)
    destination = os.path.join(archive_dir, file_name)
    
    # Handle filename collisions in archive by replacing
    if os.path.exists(destination):
        os.remove(destination)
        
    shutil.move(file_path, destination)
    return destination

