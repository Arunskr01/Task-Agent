import logging
from datetime import datetime
import csv
import os

# BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SignalLogHandler(logging.Handler):
    """Routes log records to a PySide6 signal for live GUI display.
    
    Accepts a callable (typically a Qt signal's emit method) and forwards
    every formatted log message through it, enabling real-time log capture
    from any module in the processing pipeline.
    """
    def __init__(self, signal_emit):
        super().__init__()
        self.signal_emit = signal_emit

    def emit(self, record):
        try:
            msg = self.format(record)
            self.signal_emit(msg)
        except Exception:
            self.handleError(record)

def get_logger(name: str = __name__) -> logging.Logger:
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler()

        formatter = logging.Formatter(
            fmt="%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s",
            datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)

        logger.addHandler(handler)

    return logger


def log_to_csv(BASE_DIR, start_time, file_name, log_type, status, remarks):

    if isinstance(start_time, datetime):
        run_timestamp = start_time.strftime("%Y%m%d_%H%M%S")
        start_time_str = start_time.strftime("%H:%M:%S")
    else:
        run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        start_time_str = str(start_time)

    log_csv_path = os.path.join(BASE_DIR, "output", "logs", f"log_{run_timestamp}.csv")

    headers = ["Start Time", "End Time", "File Name", "Log Type", "Status", "Remarks"]

    try:
        os.makedirs(os.path.dirname(log_csv_path), exist_ok=True)

        file_exists = os.path.isfile(log_csv_path)

        with open(log_csv_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)

            if not file_exists:
                writer.writeheader()

            now = datetime.now().strftime("%H:%M:%S")

            writer.writerow({
                "Start Time": start_time_str,
                "End Time": now,
                "File Name": file_name,
                "Log Type": log_type,
                "Status": status,
                "Remarks": remarks
            })

    except Exception as e:
        print(f"Could not update log file: {e}")


