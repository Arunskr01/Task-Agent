import pandas as pd
import numpy as np

# CONFIG 
DIGITAL_EXCEL_PATH = r"D:\CodeBase\TestWorks\DigitalPDF\data\input_1_Digital.xlsx"
OCR_EXCEL_PATH = r"D:\CodeBase\TestWorks\DigitalPDF\data\input_1_OCR.xlsx"
OUTPUT_EXCEL_PATH = r"D:\CodeBase\TestWorks\DigitalPDF\data\input_1_merged1.xlsx"

THRESHOLD = 100  # max allowed difference (in same units as left/top)

# Coordinate columns used for similarity comparison
COORD_COLS = ["left", "top"]


def find_unmatched_ocr_rows(digital_df: pd.DataFrame, ocr_df: pd.DataFrame,
                             coord_cols: list, threshold: float) -> pd.DataFrame:
    """
    Return the subset of ocr_df rows that do NOT have a position-matching
    counterpart in digital_df.

    A digital row is considered a "match" for an OCR row if the absolute
    difference is within `threshold` for ALL of the coordinate columns
    simultaneously (left, top).
    """
    # Extract coordinate values as numpy arrays for fast vectorized comparison
    digital_coords = digital_df[coord_cols].to_numpy(dtype=float)   # shape (D, 2)
    ocr_coords = ocr_df[coord_cols].to_numpy(dtype=float)           # shape (O, 2)

    # For each OCR row, compare against every digital row at once using
    # broadcasting: result shape -> (O, D, 2)
    diff = np.abs(ocr_coords[:, np.newaxis, :] - digital_coords[np.newaxis, :, :])

    # A digital row is a valid match only if BOTH left and top diffs are
    # within the threshold -> shape (O, D)
    within_threshold = np.all(diff <= threshold, axis=2)

    # An OCR row has a match if AT LEAST ONE digital row satisfies the
    # condition above -> shape (O,)
    has_match = np.any(within_threshold, axis=1)

    # Rows in OCR with no matching digital row are the "extra" rows
    unmatched_mask = ~has_match
    return ocr_df[unmatched_mask].copy()


def merge_excels(digital_df: pd.DataFrame, ocr_df: pd.DataFrame,
                  threshold: float = THRESHOLD, coord_cols: list = COORD_COLS) -> pd.DataFrame:
    """
    Merge digital and OCR DataFrames.

    OCR rows that have no position-matching counterpart in digital_df
    are appended before the last digital row (page-end marker).

    Args:
        digital_df: DataFrame from digital (native PDF) extraction.
        ocr_df:     DataFrame from OCR extraction.
        threshold:  Max coordinate difference for a match.
        coord_cols: Coordinate columns used for similarity comparison.

    Returns:
        Merged pd.DataFrame.
    """
    # Sanity check: coordinate columns must exist in both frames
    for col in coord_cols:
        if col not in digital_df.columns:
            raise ValueError(f"Column '{col}' not found in digital DataFrame.")
        if col not in ocr_df.columns:
            raise ValueError(f"Column '{col}' not found in OCR DataFrame.")

    # Find OCR rows that have no position-similar counterpart in the digital excel
    extra_ocr_rows = find_unmatched_ocr_rows(digital_df, ocr_df, coord_cols, threshold)

    # Union of all columns from both dataframes (keeps every column from both files)
    all_columns = list(digital_df.columns) + [c for c in ocr_df.columns if c not in digital_df.columns]

    digital_df = digital_df.reindex(columns=all_columns)
    extra_ocr_rows = extra_ocr_rows.reindex(columns=all_columns)

    # Insert extra OCR rows just before the last digital row so that the
    # digital file's final row (typically the page-end marker) stays last.
    if len(digital_df) > 0:
        merged_df = pd.concat(
            [digital_df.iloc[:-1], extra_ocr_rows, digital_df.iloc[-1:]],
            ignore_index=True,
        )
    else:
        merged_df = extra_ocr_rows.copy()

    return merged_df


if __name__ == "__main__":
    digital_df = pd.read_excel(DIGITAL_EXCEL_PATH)
    ocr_df = pd.read_excel(OCR_EXCEL_PATH)
    merged_df = merge_excels(
        digital_df=digital_df,
        ocr_df=ocr_df,
        threshold=THRESHOLD,
        coord_cols=COORD_COLS,
    )
    merged_df.to_excel(OUTPUT_EXCEL_PATH, index=False)