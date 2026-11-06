"""Initialize utils module."""
from .logger import get_logger, log_to_csv, SignalLogHandler
from .file_manager import (
    setup_base_folders,
    get_cache_folders,
    create_cache_folders,
    delete_cache_folder,
    get_input_files,
    move_to_archive
)
from .db_operations import (
    Insert_Execution_Master,
    get_customer_name,
    get_model_config,
    get_model_prompt,
    get_project_id,
    get_vision_grade,
    Update_Execution_Master,
    Insert_Document_Table,
    Update_Document_Table,
    Insert_Execution_Audit,
    Insert_Header_Data_Output,
    Insert_Header_Data_Output_Batch,
    Update_Header_Data_Output,
    get_header_data_map,
    get_iq_lens_fields,
    Insert_Table_Data_Output,
    Insert_Table_Data_Output_Batch,
    Update_Table_Data_Output,
    get_table_data_map,
    get_db_connection,
    Get_Execution_Status,
    Get_Execution_Audits,
    Get_Document_Status,
    Get_Document_Result,
    Validate_API_Key,
    Check_Key_Scope,
    get_llm_config,
    get_ocr_config,
)

from .pdf_utils import extract_text_from_pdf, _get_page_images_base64
