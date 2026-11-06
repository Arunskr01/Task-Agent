import pandas as pd
from pathlib import Path

def read_excel_to_text(file_path: Path) -> str:
    """
    Reads all sheets using pandas. Drops fully empty rows, fills NaN with empty string.
    Returns each sheet serialized as CSV text with a sheet name header.
    """
    # Read all sheets into a dictionary of DataFrames
    excel_data = pd.read_excel(file_path, sheet_name=None)

    result_text = []
    
    for sheet_name, df in excel_data.items():
        # Drop rows where all elements are missing
        df = df.dropna(how="all")
        # Fill remaining NaNs with empty string
        df = df.fillna("")
        
        # Add a sheet header
        result_text.append(f"--- Sheet: {sheet_name} ---")
        
        # Convert DataFrame to CSV text (no index)
        # print(df.to_string(index=False))
        # csv_text = df.to_csv(index=False, sep='\t')
        csv_text = df.to_string(index=False)
        result_text.append(csv_text)
        result_text.append("\n")
        
    return "\n".join(result_text)
