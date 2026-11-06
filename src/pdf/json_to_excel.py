import pandas as pd
import os
from pathlib import Path

def convert_json_to_excel(json_data: dict, original_filename: str, output_path: str):
    """
    Parses a JSON dictionary and converts it to an Excel file with two sheets:
    """
    original_path = Path(original_filename)
    excel_filename = original_path.name
    output_path = os.path.join(output_path, excel_filename)
    
    header_data = {}
    tables_dict = {}
    
    # 1. Check if the JSON follows the common "Sheets" -> "Headers" / "Tables" pattern
    is_standard_schema = False
    if isinstance(json_data, dict) and "Sheets" in json_data and isinstance(json_data["Sheets"], list):
        is_standard_schema = True
        for sheet in json_data["Sheets"]:
            if "Headers" in sheet and isinstance(sheet["Headers"], dict):
                for k, v in sheet["Headers"].items():
                    # Save exact key as requested
                    header_data[k] = v
            
            # Legacy Single Table
            if "Table" in sheet and isinstance(sheet["Table"], list):
                if "Table 1" not in tables_dict:
                    tables_dict["Table 1"] = []
                tables_dict["Table 1"].extend(sheet["Table"])
                
            # New Multi-Table
            if "Tables" in sheet and isinstance(sheet["Tables"], dict):
                for t_name, t_rows in sheet["Tables"].items():
                    if isinstance(t_rows, list):
                        if t_name not in tables_dict:
                            tables_dict[t_name] = []
                        tables_dict[t_name].extend(t_rows)
                
    # 2. Fallback to recursive strategy if the above schema wasn't found
    if not is_standard_schema:
        def extract_recursively(data):
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, list):
                        # Avoid treating lists containing complex objects (like dicts of lists) as flat tables
                        if len(v) > 0 and isinstance(v[0], dict) and any(isinstance(val, (dict, list)) for val in v[0].values()):
                            for item in v:
                                extract_recursively(item)
                        else:
                            if "Table 1" not in tables_dict:
                                tables_dict["Table 1"] = []
                            tables_dict["Table 1"].extend(v)
                    elif isinstance(v, dict):
                        extract_recursively(v)
                    else:
                        header_data[k] = v
            elif isinstance(data, list):
                if "Table 1" not in tables_dict:
                    tables_dict["Table 1"] = []
                tables_dict["Table 1"].extend(data)
                
        extract_recursively(json_data)
    
    # Build header dataframe
    if header_data:
        df_headers = pd.DataFrame(list(header_data.items()), columns=["Key", "Value"])
    else:
        df_headers = pd.DataFrame(columns=["Key", "Value"])

    import re
    
    # Write to Excel
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df_headers.to_excel(writer, sheet_name="Headers", index=False)
        
        if not tables_dict:
            # Fallback if no tables exist
            pd.DataFrame().to_excel(writer, sheet_name="Table", index=False)
        else:
            for t_name, t_rows in tables_dict.items():
                # Sanitize sheet name: <= 31 chars, no invalid chars
                safe_name = re.sub(r'[\\/*?:\[\]]', '', str(t_name))[:31].strip()
                if not safe_name:
                    safe_name = "Table"
                
                # Build dataframe for table
                if t_rows:
                    if not isinstance(t_rows[0], dict):
                        t_rows = [{"Value": item} for item in t_rows]
                    df_table = pd.DataFrame(t_rows)
                else:
                    df_table = pd.DataFrame()
                    
                df_table.to_excel(writer, sheet_name=safe_name, index=False)

