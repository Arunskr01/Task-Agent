import os

def get_file_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.pdf':
        return 'pdf'
    elif ext in ['.jpg', '.jpeg', '.png']:
        return 'image'
    elif ext in ['.xls', '.xlsx', '.csv']:
        return 'excel'
    elif ext in ['.doc', '.docx']:
        return 'word'
    elif ext == '.eml':
        return 'email'
        
    return 'unknown'
