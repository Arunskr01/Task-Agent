"""
db_operations.py
----------------
Utility functions for all database INSERT and UPDATE operations
performed at execution time by the AgenticDocuZone Engine.

Place this file in:  src/utils/db_operations.py

Usage in your main code:
    from src.utils.db_operations import (
        Insert_Execution_Master,
        Update_Execution_Master,
        Insert_Document_Table,
        Update_Document_Table,
        Insert_Execution_Audit,
        Insert_Header_Data_Output,
        Update_Header_Data_Output,
        Insert_Table_Data_Output,
        Update_Table_Data_Output,
        get_db_connection,
    )
"""

import pyodbc
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database Connection
# ---------------------------------------------------------------------------

def get_db_connection(
    server: str,
    database: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    trusted_connection: bool = False,
) -> pyodbc.Connection:
    """
    Creates and returns a pyodbc connection to the SQL Server database.

    Args:
        server          : SQL Server host (e.g. "localhost" or "SERVER\\INSTANCE")
        database        : Database name (e.g. "DocuzoneDevDB")
        username        : SQL login username (used when trusted_connection=False)
        password        : SQL login password (used when trusted_connection=False)
        trusted_connection : Use Windows Authentication if True

    Returns:
        pyodbc.Connection

    Example:
        conn = get_db_connection(
            server="localhost",
            database="DocuzoneDevDB",
            trusted_connection=True
        )
    """
    if trusted_connection:
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"Trusted_Connection=yes;"
        )
    else:
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
        )
    try:
        conn = pyodbc.connect(conn_str)
        logger.info(f"[DB] Connected to database '{database}' on '{server}'.")
        return conn
    except pyodbc.Error as e:
        logger.error(f"[DB] Connection failed: {e}")
        raise


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _now() -> datetime:
    """Returns current datetime (used for Created_Date / Updated_Date)."""
    return datetime.now()


# ===========================================================================
# API AUTHENTICATION & SCOPING
# ===========================================================================

def Validate_API_Key(conn: pyodbc.Connection, raw_key: str) -> Optional[dict]:
    """
    Looks up the key by exact match on the plaintext [Key] column.
    Returns None if not found, inactive, or expired.
    On success, updates Last_Used_Date and returns API_Key_ID and Customer_ID.
    """
    sql_check = """
        SELECT [API_Key_ID], [Customer_ID]
        FROM [dbo].[API_Keys]
        WHERE [Key] = ? AND [Is_Active] = 1 
          AND ([Expiry_Date] IS NULL OR [Expiry_Date] > GETDATE())
    """
    sql_update = """
        UPDATE [dbo].[API_Keys]
        SET [Last_Used_Date] = GETDATE()
        WHERE [API_Key_ID] = ?
    """
    try:
        cursor = conn.cursor()
        cursor.execute(sql_check, (raw_key,))
        row = cursor.fetchone()
        if not row:
            return None
        
        api_key_id = row[0]
        customer_id = row[1]
        
        # Update Last_Used_Date
        cursor.execute(sql_update, (api_key_id,))
        conn.commit()
        
        return {"API_Key_ID": api_key_id, "Customer_ID": customer_id}
    except pyodbc.Error as e:
        logger.error(f"[DB] Validate_API_Key failed: {e}")
        return None


def Check_Key_Scope(conn: pyodbc.Connection, api_key_id: int, model_id: int) -> bool:
    """
    Validates if the given API key is scoped to access the specified model.
    """
    sql = """
        SELECT 1
        FROM [dbo].[Model] m
        JOIN [dbo].[Project] p ON m.[Project_ID] = p.[Project_ID]
        JOIN [dbo].[API_Keys] ak ON ak.[Customer_ID] = p.[Customer_ID]
        JOIN [dbo].[API_Key_Scope] aks ON aks.[API_Key_ID] = ak.[API_Key_ID]
        WHERE m.[Model_ID] = ? 
          AND ak.[API_Key_ID] = ?
          AND aks.[Project_ID] = p.[Project_ID]
          AND (aks.[Model_ID] IS NULL OR aks.[Model_ID] = ?)
    """
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (model_id, api_key_id, model_id))
        row = cursor.fetchone()
        return bool(row)
    except pyodbc.Error as e:
        logger.error(f"[DB] Check_Key_Scope failed: {e}")
        return False


def get_customer_name(conn: pyodbc.Connection, model_id: int) -> str:
    sql = """
        SELECT c.[Customer_Name]
        FROM [dbo].[Model] m
        JOIN [dbo].[Project] p ON m.[Project_ID] = p.[Project_ID]
        JOIN [dbo].[Customer] c ON p.[Customer_ID] = c.[Customer_ID]
        WHERE m.[Model_ID] = ?
    """
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (model_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"No customer found for Model_ID={model_id}")
        customer_name = row[0]
        logger.info(f"[DB] get_customer_name → Model_ID={model_id}, Name='{customer_name}'")
        return customer_name
    except pyodbc.Error as e:
        logger.error(f"[DB] get_customer_name failed: {e}")
def get_model_config(conn: pyodbc.Connection, model_key_or_id: str) -> Optional[dict]:
    """
    Fetches model configuration from the Model table by Model_Key or legacy numeric Model_ID.
    
    If model_key_or_id is purely numeric (legacy config.dat), queries by:
        WHERE Model_ID = ?
    Otherwise, queries by:
        WHERE Model_Key = ? AND Status = 'Active'

    Returns:
        dict with keys: Model_ID, Project_ID, Model_Name, Prompt, Special_Prompt, User_Prompt, Vision_Grade, Status
        or None if no matching active record is found.
    """
    key_str = str(model_key_or_id).strip()
    if not key_str:
        return None

    if key_str.isdigit():
        sql = """
            SELECT [Model_ID], [Project_ID], [Model_Name], [Prompt], [Special_Prompt], [Vision_Grade], [Status], [LLM_Config_ID], [Vision_Prompt]
            FROM [dbo].[Model]
            WHERE [Model_ID] = ?
        """
        params = (int(key_str),)
    else:
        sql = """
            SELECT [Model_ID], [Project_ID], [Model_Name], [Prompt], [Special_Prompt], [Vision_Grade], [Status], [LLM_Config_ID], [Vision_Prompt]
            FROM [dbo].[Model]
            WHERE [Model_Key] = ? AND [Status] = 'Active'
        """
        params = (key_str,)

    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        row = cursor.fetchone()
        if not row:
            logger.warning(f"[DB] No record found in Model table for: '{key_str}'")
            return None

        # Verify active status
        status = row[6]
        if status is not None and str(status).strip().lower() != "active":
            logger.warning(f"[DB] Model record found for '{key_str}', but Status is '{status}' (expected 'Active').")
            return None

        prompt = row[3] or ""
        special_prompt = row[4]
        combined_prompt = f"{prompt}\n\n{special_prompt}".strip() if special_prompt else prompt
        vision_prompt = row[8] if (len(row) > 8 and row[8] is not None) else None

        model_dict = {
            "Model_ID": row[0],
            "Project_ID": row[1],
            "Model_Name": row[2],
            "Prompt": prompt,
            "Special_Prompt": special_prompt,
            "User_Prompt": combined_prompt,
            "Vision_Grade": row[5] if row[5] else "Aggressive",
            "Status": status,
            "LLM_Config_ID": row[7] if (len(row) > 7 and row[7] is not None) else 1,
            "Vision_Prompt": vision_prompt
        }
        logger.info(f"[DB] get_model_config → Model_ID={model_dict['Model_ID']}, Project_ID={model_dict['Project_ID']}, Name='{model_dict['Model_Name']}', Status='{status}', LLM_Config_ID={model_dict['LLM_Config_ID']}, Has_Vision_Prompt={bool(vision_prompt)}")
        return model_dict
    except pyodbc.Error as e:
        logger.error(f"[DB] get_model_config failed: {e}")
        raise


def get_model_prompt(conn: pyodbc.Connection, model_id: int) -> str:
    """
    Fetches the user prompt from the Model table.
    """
    sql = """
        SELECT [Prompt]
        FROM [dbo].[Model]
        WHERE [Model_ID] = ?
    """
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (model_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"No prompt found for Model_ID={model_id}")
        prompt = row[0]
        logger.info(f"[DB] get_model_prompt → Model_ID={model_id}")
        return prompt
    except pyodbc.Error as e:
        logger.error(f"[DB] get_model_prompt failed: {e}")
        raise

def get_project_id(conn: pyodbc.Connection, model_id: int) -> int:
    """
    Fetches the Project_ID from the Model table.
    """
    sql = """
        SELECT [Project_ID]
        FROM [dbo].[Model]
        WHERE [Model_ID] = ?
    """
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (model_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"No project found for Model_ID={model_id}")
        project_id = row[0]
        logger.info(f"[DB] get_project_id → Model_ID={model_id}, Project_ID={project_id}")
        return project_id
    except pyodbc.Error as e:
        logger.error(f"[DB] get_project_id failed: {e}")
        raise

def get_vision_grade(conn: pyodbc.Connection, model_id: int) -> str:
    """
    Fetches the Vision_Grade from the Model table.
    """
    sql = """
        SELECT [Vision_Grade]
        FROM [dbo].[Model]
        WHERE [Model_ID] = ?
    """
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (model_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"No Vision_Grade found for Model_ID={model_id}")
        vision_grade = row[0]
        logger.info(f"[DB] get_vision_grade → Model_ID={model_id}, Vision_Grade={vision_grade}")
        return vision_grade
    except pyodbc.Error as e:
        logger.error(f"[DB] get_vision_grade failed: {e}")
        raise


# ===========================================================================
# TABLE: Execution_Master
# ===========================================================================
#
# LOGIC:
#   INSERT  — called once at the very start of a new execution run.
#             Execution_ID is IDENTITY so it is NOT a parameter.
#             Returns the newly generated Execution_ID.
#
#   UPDATE  — called at the end of the run (or on failure) to stamp
#             End_Time, final Execution_Status, and optional Remarks.
#
# Columns:
#   PK  : Execution_ID  (bigint, IDENTITY — auto-generated, not passed in)
#   FK  : Project_ID    (int,    NOT NULL)
#   FK  : Model_ID      (int,    NOT NULL)
#       : Triggered_By  (varchar(100), NOT NULL)
#       : Trigger_Source(varchar(255), NULL)
#       : Input_Folder  (nvarchar(max),NULL)
#       : Output_Folder (nvarchar(max),NULL)
#       : Execution_Status (varchar(50), NOT NULL)
#       : Start_Time    (datetime, NULL)
#       : End_Time      (datetime, NULL)
#       : Remarks       (nvarchar(max), NULL)
#       : Created_Date  (datetime, NOT NULL)  — auto-filled
#       : Updated_Date  (datetime, NULL)
#       : Created_By    (varchar(100), NOT NULL)
#       : Updated_By    (varchar(100), NULL)
# ===========================================================================

def Insert_Execution_Master(
    conn: pyodbc.Connection,
    Project_ID: int,
    Model_ID: int,
    Triggered_By: str,
    Execution_Status: str,
    Created_By: str,
    Trigger_Source: Optional[str] = None,
    Input_Folder: Optional[str] = None,
    Output_Folder: Optional[str] = None,
    Start_Time: Optional[datetime] = None,
    Remarks: Optional[str] = None,
) -> int:
    """
    Inserts a new row into Execution_Master at the start of an execution run.

    Returns:
        int : The newly generated Execution_ID (IDENTITY value).

    Example:
        execution_id = Insert_Execution_Master(
            conn=conn,
            Project_ID=2001,
            Model_ID=3001,
            Triggered_By="main.exe",
            Execution_Status="Running",
            Created_By="main.exe",
            Input_Folder="D:/HotFolder/input",
            Output_Folder="D:/HotFolder/output",
            Start_Time=datetime.now(),
        )
    """
    sql = """
        INSERT INTO [dbo].[Execution_Master] (
            [Project_ID], [Model_ID], [Triggered_By], [Trigger_Source],
            [Input_Folder], [Output_Folder], [Execution_Status],
            [Start_Time], [Remarks],
            [Created_Date], [Created_By]
        )
        OUTPUT INSERTED.[Execution_ID]
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        Project_ID, Model_ID, Triggered_By, Trigger_Source,
        Input_Folder, Output_Folder, Execution_Status,
        Start_Time, Remarks,
        _now(), Created_By,
    )
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        execution_id = cursor.fetchone()[0]
        conn.commit()
        logger.info(f"[DB] Insert_Execution_Master → Execution_ID={execution_id}")
        return execution_id
    except pyodbc.Error as e:
        conn.rollback()
        logger.error(f"[DB] Insert_Execution_Master failed: {e}")
        raise


def Update_Execution_Master(
    conn: pyodbc.Connection,
    Execution_ID: int,
    Execution_Status: str,
    Updated_By: str,
    End_Time: Optional[datetime] = None,
    Remarks: Optional[str] = None,
    Output_Folder: Optional[str] = None,
    No_of_Documents: Optional[int] = None,
    No_of_page: Optional[int] = None,
) -> None:
    """
    Updates Execution_Master at the end of a run (success or failure).

    Args:
        Execution_ID     : The run's primary key (returned by Insert_Execution_Master).
        Execution_Status : Final status — e.g. "Completed", "Failed", "Partial".
        Updated_By       : Identifier of the process making the update (e.g. "main.exe").
        End_Time         : Timestamp when the run finished (defaults to now if None).
        Remarks          : Optional summary / error message.
        Output_Folder    : Set/override output folder path if needed.

    Example:
        Update_Execution_Master(
            conn=conn,
            Execution_ID=execution_id,
            Execution_Status="Completed",
            Updated_By="main.exe",
            End_Time=datetime.now(),
            Remarks="3 files processed successfully.",
        )
    """
    if End_Time is None:
        End_Time = _now()

    sql = """
        UPDATE [dbo].[Execution_Master]
        SET
            [Execution_Status] = ?,
            [End_Time]         = ?,
            [Remarks]          = ?,
            [Output_Folder]    = COALESCE(?, [Output_Folder]),
            [No_of_Documents]  = COALESCE(?, [No_of_Documents]),
            [No_of_page]       = COALESCE(?, [No_of_page]),
            [Updated_Date]     = ?,
            [Updated_By]       = ?
        WHERE [Execution_ID] = ?
    """
    params = (
        Execution_Status, End_Time, Remarks,
        Output_Folder,
        No_of_Documents,
        No_of_page,
        _now(), Updated_By,
        Execution_ID,
    )
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        logger.info(f"[DB] Update_Execution_Master → Execution_ID={Execution_ID}, Status={Execution_Status}")
    except pyodbc.Error as e:
        conn.rollback()
        logger.error(f"[DB] Update_Execution_Master failed: {e}")
        raise


# ===========================================================================
# TABLE: Document_Table
# ===========================================================================
#
# LOGIC:
#   INSERT  — called once per file when it is picked up from input/.
#             Doc_ID is IDENTITY — auto-generated, returned to caller.
#
#   UPDATE  — called when the document's processing status changes
#             (e.g., "Processing" → "Completed" / "Failed").
#             Also used to set Page_Count after OCR/PDF inspection.
#
# Columns:
#   PK  : Doc_ID         (bigint, IDENTITY)
#   FK  : Execution_ID   (bigint, NOT NULL)
#       : File_Name      (varchar(500), NOT NULL)
#       : File_Path      (nvarchar(max), NOT NULL)
#       : MIME_Type      (varchar(100), NULL)
#       : File_Size_KB   (decimal(15,2), NULL)
#       : Page_Count     (int, NULL)
#       : Doc_Status     (varchar(50), NOT NULL)
#       : Created_Date   (datetime, NOT NULL)
#       : Updated_Date   (datetime, NULL)
#       : Created_By     (varchar(100), NOT NULL)
#       : Updated_By     (varchar(100), NULL)
# ===========================================================================

def Insert_Document_Table(
    conn: pyodbc.Connection,
    Execution_ID: int,
    File_Name: str,
    File_Path: str,
    Doc_Status: str,
    Created_By: str,
    MIME_Type: Optional[str] = None,
    File_Size_KB: Optional[float] = None,
    Page_Count: Optional[int] = None,
) -> int:
    """
    Inserts a new document record when a file is picked up from input/.

    Returns:
        int : The newly generated Doc_ID (IDENTITY value).

    Example:
        doc_id = Insert_Document_Table(
            conn=conn,
            Execution_ID=execution_id,
            File_Name="invoice_001.pdf",
            File_Path="D:/HotFolder/input/invoice_001.pdf",
            Doc_Status="Processing",
            Created_By="main.exe",
            MIME_Type="application/pdf",
            File_Size_KB=245.50,
        )
    """
    sql = """
        INSERT INTO [dbo].[Document_Table] (
            [Execution_ID], [File_Name], [File_Path],
            [MIME_Type], [File_Size_KB], [Page_Count],
            [Doc_Status], [Created_Date], [Created_By]
        )
        OUTPUT INSERTED.[Doc_ID]
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        Execution_ID, File_Name, File_Path,
        MIME_Type, File_Size_KB, Page_Count,
        Doc_Status, _now(), Created_By,
    )
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        doc_id = cursor.fetchone()[0]
        conn.commit()
        logger.info(f"[DB] Insert_Document_Table → Doc_ID={doc_id}, File={File_Name}")
        return doc_id
    except pyodbc.Error as e:
        conn.rollback()
        logger.error(f"[DB] Insert_Document_Table failed: {e}")
        raise


def Update_Document_Table(
    conn: pyodbc.Connection,
    Doc_ID: int,
    Doc_Status: str,
    Updated_By: str,
    Page_Count: Optional[int] = None,
    MIME_Type: Optional[str] = None,
    File_Size_KB: Optional[float] = None,
    Tokens_used: Optional[int] = None,
    Input_Tokens: Optional[int] = None,
    Output_Tokens: Optional[int] = None,
    Json_Output: Optional[str] = None,
    Text_Content: Optional[str] = None,
) -> None:
    """
    Updates a document's status and optional metadata after processing.

    Args:
        Doc_ID       : Primary key of the document row.
        Doc_Status   : New status — e.g. "Completed", "Failed", "Archived".
        Updated_By   : Process name making the update.
        Page_Count   : Set once known (after OCR / PDF read).
        MIME_Type    : Override MIME type if detected later.
        File_Size_KB : Override file size if calculated later.
        Tokens_used  : Total LLM tokens consumed.
        Input_Tokens : Input prompt tokens consumed.
        Output_Tokens: Output completion tokens consumed.
        Json_Output  : Extracted raw JSON string to store in the DB.
        Text_Content : Extracted text content preserving layout.

    Example:
        Update_Document_Table(
            conn=conn,
            Doc_ID=doc_id,
            Doc_Status="Completed",
            Updated_By="main.exe",
            Tokens_used=1800,
            Input_Tokens=1400,
            Output_Tokens=400,
            Page_Count=3,
        )
    """
    sql = """
        UPDATE [dbo].[Document_Table]
        SET
            [Doc_Status]    = ?,
            [Page_Count]    = COALESCE(?, [Page_Count]),
            [MIME_Type]     = COALESCE(?, [MIME_Type]),
            [File_Size_KB]  = COALESCE(?, [File_Size_KB]),
            [Tokens_used]   = COALESCE(?, [Tokens_used]),
            [Input_Tokens]  = COALESCE(?, [Input_Tokens]),
            [Output_Tokens] = COALESCE(?, [Output_Tokens]),
            [Json_Output]   = COALESCE(?, [Json_Output]),
            [Text_Content]  = COALESCE(?, [Text_Content]),
            [Updated_Date]  = ?,
            [Updated_By]    = ?
        WHERE [Doc_ID] = ?
    """
    params = (
        Doc_Status,
        Page_Count, MIME_Type, File_Size_KB,
        Tokens_used, Input_Tokens, Output_Tokens,
        Json_Output, Text_Content,
        _now(), Updated_By,
        Doc_ID,
    )
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        logger.info(f"[DB] Update_Document_Table → Doc_ID={Doc_ID}, Status={Doc_Status}, Tokens(Total={Tokens_used}, In={Input_Tokens}, Out={Output_Tokens})")
    except pyodbc.Error as e:
        conn.rollback()
        logger.error(f"[DB] Update_Document_Table failed: {e}")
        raise


# ===========================================================================
# TABLE: Execution_Audit
# ===========================================================================
#
# LOGIC:
#   INSERT ONLY — This is a pure append-only audit / stage log.
#                 Every pipeline stage transition writes a new row.
#                 Rows are NEVER updated after insertion.
#                 Audit_ID is IDENTITY — auto-generated, returned to caller.
#
# Columns:
#   PK  : Audit_ID       (bigint, IDENTITY)
#   FK  : Execution_ID   (bigint, NOT NULL)
#   FK  : Doc_ID         (bigint, NULL)  — NULL for execution-level stages
#   FK  : Model_ID       (int,    NOT NULL)
#       : Stage          (varchar(100), NOT NULL)
#       : Stage_Status   (varchar(50),  NOT NULL)
#       : Stage_Start    (datetime, NULL)
#       : Stage_End      (datetime, NULL)
#       : Remark         (nvarchar(max), NULL)
#       : Logged_By      (varchar(100), NULL)
#       : Created_Date   (datetime, NOT NULL)  — auto-filled
#       : Created_By     (varchar(100), NOT NULL)
# ===========================================================================

def Insert_Execution_Audit(
    conn: pyodbc.Connection,
    Execution_ID: int,
    Model_ID: int,
    Stage: str,
    Stage_Status: str,
    Created_By: str,
    Doc_ID: Optional[int] = None,
    Stage_Start: Optional[datetime] = None,
    Stage_End: Optional[datetime] = None,
    Remark: Optional[str] = None,
    Logged_By: Optional[str] = None,
) -> int:
    """
    Appends a new audit row for a pipeline stage event.
    Call this at the START and/or END of each stage to track progress.

    Returns:
        int : The newly generated Audit_ID.

    Example — log start of OCR stage:
        Insert_Execution_Audit(
            conn=conn,
            Execution_ID=execution_id,
            Model_ID=model_id,
            Stage="OCR",
            Stage_Status="Started",
            Created_By="main.exe",
            Doc_ID=doc_id,
            Stage_Start=datetime.now(),
        )

    Example — log end of LLM extraction stage:
        Insert_Execution_Audit(
            conn=conn,
            Execution_ID=execution_id,
            Model_ID=model_id,
            Stage="LLM_Extraction",
            Stage_Status="Completed",
            Created_By="main.exe",
            Doc_ID=doc_id,
            Stage_Start=stage_start_time,
            Stage_End=datetime.now(),
            Remark="Extracted 5 headers and 12 table rows.",
        )
    """
    sql = """
        INSERT INTO [dbo].[Execution_Audit] (
            [Execution_ID], [Doc_ID], [Model_ID],
            [Stage], [Stage_Status],
            [Stage_Start], [Stage_End],
            [Remark], [Logged_By],
            [Created_Date], [Created_By]
        )
        OUTPUT INSERTED.[Audit_ID]
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        Execution_ID, Doc_ID, Model_ID,
        Stage, Stage_Status,
        Stage_Start, Stage_End,
        Remark, Logged_By,
        _now(), Created_By,
    )
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        audit_id = cursor.fetchone()[0]
        conn.commit()
        logger.info(f"[DB] Insert_Execution_Audit → Audit_ID={audit_id}, Stage={Stage}, Status={Stage_Status}")
        return audit_id
    except pyodbc.Error as e:
        conn.rollback()
        logger.error(f"[DB] Insert_Execution_Audit failed: {e}")
        raise


def get_header_data_map(conn: pyodbc.Connection, model_id: int) -> dict:
    """
    Pre-fetches Header_Data definitions for a given Model_ID and returns
    a lookup dict keyed by FOI_Name -> Header_Data_ID.

    This allows callers to resolve the Header_Data_ID FK when inserting
    into Header_Data_Output.

    Returns:
        dict: {foi_name: str: header_data_id: int}
              Returns an empty dict if no definitions exist or on error.
    """
    mapping = {}
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT [Header_Data_ID], [FOI_Name] "
            "FROM [dbo].[Header_Data] "
            "WHERE [Model_ID] = ? AND [Status] = 'Active'",
            model_id
        )
        for row in cursor.fetchall():
            hd_id, foi_name = row[0], row[1]
            mapping[str(foi_name).strip()] = hd_id
        logger.info(f"[DB] get_header_data_map → Loaded {len(mapping)} field definitions for Model_ID={model_id}")
    except pyodbc.Error as e:
        logger.warning(f"[DB] get_header_data_map failed (non-fatal): {e}")
    return mapping


def get_iq_lens_fields(conn: pyodbc.Connection, model_id: int) -> list:
    """
    Fetches the list of FOI_Name strings configured for IQ Lens (IQ_Lens = 1)
    for a given Model_ID. Only active fields are returned.

    Returns:
        list[str]: Field names requiring IQ Lens visual processing.
    """
    fields = []
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT [FOI_Name] "
            "FROM [dbo].[Header_Data] "
            "WHERE [Model_ID] = ? AND [IQ_Lens] = 1 AND [Status] = 'Active'",
            model_id
        )
        for row in cursor.fetchall():
            if row[0]:
                fields.append(str(row[0]).strip())
        logger.info(f"[DB] get_iq_lens_fields → Found {len(fields)} IQ Lens field(s) for Model_ID={model_id}")
    except pyodbc.Error as e:
        logger.warning(f"[DB] get_iq_lens_fields failed (non-fatal): {e}")
    return fields


# ===========================================================================
# TABLE: Header_Data_Output
# ===========================================================================
#
# LOGIC:
#   INSERT ONLY — One row per extracted header field per document.
#                 Written after the LLM returns its JSON response.
#                 Header_Output_ID is IDENTITY — auto-generated, returned.
#
#   UPDATE       — Review-related columns (Review_Status, Reviewed_By,
#                  Corrected_Value) will be updated from the web UI
#                  after human review. The exe only INSERTs.
#                  The Update function is provided here for completeness
#                  so the same utils file can serve the web app too.
#
# Columns:
#   PK  : Header_Output_ID  (bigint, IDENTITY)
#   FK  : Execution_ID      (bigint, NOT NULL)
#   FK  : Model_ID          (int,    NOT NULL)
#   FK  : Header_Data_ID    (int,    NULL)
#   FK  : Doc_ID            (bigint, NULL)
#       : FOI_Name          (varchar(255), NOT NULL)  — Field Of Interest name
#       : Extracted_Value   (nvarchar(max), NULL)
#       : Page_Number       (int, NULL)
#       : Review_Status     (varchar(50), NOT NULL, default='Pending')
#       : Reviewed_By       (varchar(100), NULL)
#       : Corrected_Value   (nvarchar(max), NULL)
#       : Created_Date      (datetime, NOT NULL)
#       : Updated_Date      (datetime, NULL)
#       : Created_By        (varchar(100), NOT NULL)
#       : Updated_By        (varchar(100), NULL)
# ===========================================================================

def Insert_Header_Data_Output(
    conn: pyodbc.Connection,
    Execution_ID: int,
    Model_ID: int,
    FOI_Name: str,
    Review_Status: str,
    Created_By: str,
    Header_Data_ID: Optional[int] = None,
    Doc_ID: Optional[int] = None,
    Extracted_Value: Optional[str] = None,
    Page_Number: Optional[int] = None,
    commit: bool = True,
) -> int:
    """
    Inserts one extracted header field result row.
    Call this once per header field returned in the LLM JSON response.

    Returns:
        int : The newly generated Header_Output_ID.

    Example:
        header_output_id = Insert_Header_Data_Output(
            conn=conn,
            Execution_ID=execution_id,
            Model_ID=model_id,
            Doc_ID=doc_id,
            Header_Data_ID=header_data_id,   # FK to Header_Data config table
            FOI_Name="Invoice Number",
            Extracted_Value="INV-2024-00123",
            Page_Number=1,
            Review_Status="Pending",
            Created_By="main.exe",
        )
    """
    sql = """
        INSERT INTO [dbo].[Header_Data_Output] (
            [Execution_ID], [Model_ID], [Header_Data_ID], [Doc_ID],
            [FOI_Name], [Extracted_Value], [Page_Number],
            [Review_Status],
            [Created_Date], [Created_By]
        )
        OUTPUT INSERTED.[Header_Output_ID]
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        Execution_ID, Model_ID, Header_Data_ID, Doc_ID,
        FOI_Name, Extracted_Value, Page_Number,
        Review_Status,
        _now(), Created_By,
    )
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        header_output_id = cursor.fetchone()[0]
        if commit:
            conn.commit()
        logger.info(f"[DB] Insert_Header_Data_Output → Header_Output_ID={header_output_id}, FOI={FOI_Name}")
        return header_output_id
    except pyodbc.Error as e:
        conn.rollback()
        logger.error(f"[DB] Insert_Header_Data_Output failed: {e}")
        raise


def Insert_Header_Data_Output_Batch(
    conn: pyodbc.Connection,
    records: list,
    commit: bool = True,
    chunk_size: int = 100,
) -> list:
    """
    Inserts multiple extracted header field rows in batches using multi-row VALUES
    and OUTPUT INSERTED.[Header_Output_ID].

    Args:
        conn: Active pyodbc Connection.
        records: List of dicts (or tuples). Dict keys:
                 Execution_ID, Model_ID, Header_Data_ID, Doc_ID,
                 FOI_Name, Extracted_Value, Page_Number, Review_Status, Created_By,
                 (optional: Created_Date).
        commit: If True, commits the transaction after all chunks are inserted.
        chunk_size: Number of rows per multi-row INSERT (default 100, well under
                    SQL Server's 2100 parameter limit).

    Returns:
        list[int]: All newly generated Header_Output_IDs in insertion order.
    """
    if not records:
        return []

    inserted_ids: list[int] = []
    created_date = _now()

    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]

        row_placeholders = "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        values_clause = ", ".join([row_placeholders] * len(chunk))

        sql = f"""
            INSERT INTO [dbo].[Header_Data_Output] (
                [Execution_ID], [Model_ID], [Header_Data_ID], [Doc_ID],
                [FOI_Name], [Extracted_Value], [Page_Number],
                [Review_Status],
                [Created_Date], [Created_By]
            )
            OUTPUT INSERTED.[Header_Output_ID]
            VALUES {values_clause}
        """

        params = []
        for r in chunk:
            if isinstance(r, dict):
                params.extend([
                    r.get("Execution_ID"),
                    r.get("Model_ID"),
                    r.get("Header_Data_ID"),
                    r.get("Doc_ID"),
                    r.get("FOI_Name"),
                    r.get("Extracted_Value"),
                    r.get("Page_Number"),
                    r.get("Review_Status", "Pending"),
                    r.get("Created_Date", created_date),
                    r.get("Created_By"),
                ])
            else:
                params.extend(r)

        try:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            inserted_ids.extend([row[0] for row in rows])
        except pyodbc.Error as batch_err:
            conn.rollback()
            logger.warning(
                f"[DB] Batch insert failed for header chunk {i // chunk_size + 1} ({batch_err}). "
                f"Starting diagnostic sweep to isolate failing header..."
            )
            single_sql = """
                INSERT INTO [dbo].[Header_Data_Output] (
                    [Execution_ID], [Model_ID], [Header_Data_ID], [Doc_ID],
                    [FOI_Name], [Extracted_Value], [Page_Number],
                    [Review_Status],
                    [Created_Date], [Created_By]
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            diag_cursor = conn.cursor()
            for r in chunk:
                try:
                    if isinstance(r, dict):
                        diag_params = (
                            r.get("Execution_ID"),
                            r.get("Model_ID"),
                            r.get("Header_Data_ID"),
                            r.get("Doc_ID"),
                            r.get("FOI_Name"),
                            r.get("Extracted_Value"),
                            r.get("Page_Number"),
                            r.get("Review_Status", "Pending"),
                            r.get("Created_Date", created_date),
                            r.get("Created_By"),
                        )
                    else:
                        diag_params = r
                    diag_cursor.execute(single_sql, diag_params)
                except pyodbc.Error as cell_err:
                    conn.rollback()
                    foi_name = r.get("FOI_Name") if isinstance(r, dict) else r[4]
                    extracted_val = r.get("Extracted_Value") if isinstance(r, dict) else r[5]
                    page_num = r.get("Page_Number") if isinstance(r, dict) else r[6]
                    logger.error(
                        f"[DB ERROR PINPOINTED] Header field insertion failed: "
                        f"FOI_Name='{foi_name}', Extracted_Value='{extracted_val}', "
                        f"Page_Number={page_num}. Reason: {cell_err}"
                    )
                    raise cell_err
            raise batch_err

    if commit:
        conn.commit()

    logger.info(f"[DB] Insert_Header_Data_Output_Batch → Successfully inserted {len(inserted_ids)} headers.")
    return inserted_ids


def Update_Header_Data_Output(
    conn: pyodbc.Connection,
    Header_Output_ID: int,
    Updated_By: str,
    Review_Status: Optional[str] = None,
    Reviewed_By: Optional[str] = None,
    Corrected_Value: Optional[str] = None,
    Extracted_Value: Optional[str] = None,
) -> None:
    """
    Updates review / correction fields on a header output row.
    Primarily called by the web UI after human review, but included
    here so the same utils module serves both the exe and the web app.

    Example:
        Update_Header_Data_Output(
            conn=conn,
            Header_Output_ID=header_output_id,
            Review_Status="Approved",
            Reviewed_By="john.doe",
            Updated_By="AgenticCR_WebApp",
        )
    """
    sql = """
        UPDATE [dbo].[Header_Data_Output]
        SET
            [Review_Status]   = COALESCE(?, [Review_Status]),
            [Reviewed_By]     = COALESCE(?, [Reviewed_By]),
            [Corrected_Value] = COALESCE(?, [Corrected_Value]),
            [Extracted_Value] = COALESCE(?, [Extracted_Value]),
            [Updated_Date]    = ?,
            [Updated_By]      = ?
        WHERE [Header_Output_ID] = ?
    """
    params = (
        Review_Status, Reviewed_By, Corrected_Value, Extracted_Value,
        _now(), Updated_By,
        Header_Output_ID,
    )
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        logger.info(f"[DB] Update_Header_Data_Output → Header_Output_ID={Header_Output_ID}")
    except pyodbc.Error as e:
        conn.rollback()
        logger.error(f"[DB] Update_Header_Data_Output failed: {e}")
        raise


def get_table_data_map(conn: pyodbc.Connection, model_id: int) -> dict:
    """
    Pre-fetches Table_Data definitions for a given Model_ID and returns
    a lookup dict keyed by (Table_Name, FOT_Name) -> Table_Data_ID.

    This allows callers to resolve the Table_Data_ID FK when inserting
    into Table_Data_Output.

    Returns:
        dict: {(table_name: str, fot_name: str): table_data_id: int}
              Returns an empty dict if no definitions exist or on error.
    """
    mapping = {}
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT [Table_Data_ID], [Table_Name], [FOT_Name] "
            "FROM [dbo].[Table_Data] "
            "WHERE [Model_ID] = ? AND [Status] = 'Active'",
            model_id
        )
        for row in cursor.fetchall():
            td_id, t_name, fot_name = row[0], row[1], row[2]
            key = (str(t_name).strip() if t_name else "", str(fot_name).strip())
            mapping[key] = td_id
        logger.info(f"[DB] get_table_data_map → Loaded {len(mapping)} field definitions for Model_ID={model_id}")
    except pyodbc.Error as e:
        logger.warning(f"[DB] get_table_data_map failed (non-fatal): {e}")
    return mapping


# ===========================================================================
# TABLE: Table_Data_Output
# ===========================================================================
#
# LOGIC:
#   INSERT ONLY — One row per cell (column × row index) of the extracted
#                 table data per document.
#                 Written after the LLM returns its JSON response.
#                 Table_Output_ID is IDENTITY — auto-generated, returned.
#
#   UPDATE       — Like Header_Data_Output, review columns are updated
#                  from the web UI. The exe only INSERTs.
#                  Update function provided here for completeness.
#
# Columns:
#   PK  : Table_Output_ID  (bigint, IDENTITY)
#   FK  : Execution_ID     (bigint, NOT NULL)
#   FK  : Model_ID         (int,    NOT NULL)
#   FK  : Table_Data_ID    (int,    NULL)
#   FK  : Doc_ID           (bigint, NULL)
#       : Row_Index         (int,   NOT NULL)
#       : FOT_Name          (varchar(255), NOT NULL)  — Field Of Table name
#       : Extracted_Value   (nvarchar(max), NULL)
#       : Page_Number       (int, NULL)
#       : Review_Status     (varchar(50), NOT NULL, default='Pending')
#       : Reviewed_By       (varchar(100), NULL)
#       : Corrected_Value   (nvarchar(max), NULL)
#       : Created_Date      (datetime, NOT NULL)
#       : Updated_Date      (datetime, NULL)
#       : Created_By        (varchar(100), NOT NULL)
#       : Updated_By        (varchar(100), NULL)
# ===========================================================================

def Insert_Table_Data_Output(
    conn: pyodbc.Connection,
    Execution_ID: int,
    Model_ID: int,
    Row_Index: int,
    FOT_Name: str,
    Review_Status: str,
    Created_By: str,
    Table_Data_ID: Optional[int] = None,
    Doc_ID: Optional[int] = None,
    Extracted_Value: Optional[str] = None,
    Page_Number: Optional[int] = None,
    commit: bool = True,
) -> int:
    """
    Inserts one extracted table cell result row.
    Call this in a loop — once per (row_index × column) in the LLM JSON table output.

    Returns:
        int : The newly generated Table_Output_ID.

    Example:
        for row_idx, row in enumerate(extracted_table_rows):
            for col_name, cell_value in row.items():
                Insert_Table_Data_Output(
                    conn=conn,
                    Execution_ID=execution_id,
                    Model_ID=model_id,
                    Doc_ID=doc_id,
                    Table_Data_ID=table_data_id,   # FK to Table_Data config table
                    Row_Index=row_idx,
                    FOT_Name=col_name,
                    Extracted_Value=str(cell_value),
                    Page_Number=1,
                    Review_Status="Pending",
                    Created_By="main.exe",
                )
    """
    sql = """
        INSERT INTO [dbo].[Table_Data_Output] (
            [Execution_ID], [Model_ID], [Table_Data_ID], [Doc_ID],
            [Row_Index], [FOT_Name], [Extracted_Value], [Page_Number],
            [Review_Status],
            [Created_Date], [Created_By]
        )
        OUTPUT INSERTED.[Table_Output_ID]
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        Execution_ID, Model_ID, Table_Data_ID, Doc_ID,
        Row_Index, FOT_Name, Extracted_Value, Page_Number,
        Review_Status,
        _now(), Created_By,
    )
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        table_output_id = cursor.fetchone()[0]
        if commit:
            conn.commit()
        logger.info(f"[DB] Insert_Table_Data_Output → Table_Output_ID={table_output_id}, Row={Row_Index}, FOT={FOT_Name}")
        return table_output_id
    except pyodbc.Error as e:
        conn.rollback()
        logger.error(f"[DB] Insert_Table_Data_Output failed: {e}")
        raise


def Insert_Table_Data_Output_Batch(
    conn: pyodbc.Connection,
    records: list,
    commit: bool = True,
    chunk_size: int = 100,
) -> list:
    """
    Inserts multiple extracted table cell rows in batches using multi-row VALUES
    and OUTPUT INSERTED.[Table_Output_ID].

    Args:
        conn: Active pyodbc Connection.
        records: List of dicts (or tuples). Dict keys:
                 Execution_ID, Model_ID, Table_Data_ID, Doc_ID, Table_Number, Table_Name, Row_Index,
                 FOT_Name, Extracted_Value, Page_Number, Review_Status, Created_By,
                 (optional: Created_Date).
        commit: If True, commits the transaction after all chunks are inserted.
        chunk_size: Number of rows per multi-row INSERT (default 100, well under
                    SQL Server's 2100 parameter limit).

    Returns:
        list[int]: All newly generated Table_Output_IDs in insertion order.
    """
    if not records:
        return []

    inserted_ids: list[int] = []
    created_date = _now()

    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]

        row_placeholders = "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        values_clause = ", ".join([row_placeholders] * len(chunk))

        sql = f"""
            INSERT INTO [dbo].[Table_Data_Output] (
                [Execution_ID], [Model_ID], [Table_Data_ID], [Doc_ID],
                [Table_Number], [Table_Name],
                [Row_Index], [FOT_Name], [Extracted_Value], [Page_Number],
                [Review_Status],
                [Created_Date], [Created_By]
            )
            OUTPUT INSERTED.[Table_Output_ID]
            VALUES {values_clause}
        """

        params = []
        for r in chunk:
            if isinstance(r, dict):
                params.extend([
                    r.get("Execution_ID"),
                    r.get("Model_ID"),
                    r.get("Table_Data_ID"),
                    r.get("Doc_ID"),
                    r.get("Table_Number"),
                    r.get("Table_Name"),
                    r.get("Row_Index"),
                    r.get("FOT_Name"),
                    r.get("Extracted_Value"),
                    r.get("Page_Number"),
                    r.get("Review_Status", "Pending"),
                    r.get("Created_Date", created_date),
                    r.get("Created_By"),
                ])
            else:
                params.extend(r)

        try:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            inserted_ids.extend([row[0] for row in rows])
        except pyodbc.Error as batch_err:
            conn.rollback()
            logger.warning(
                f"[DB] Batch insert failed for table chunk {i // chunk_size + 1} ({batch_err}). "
                f"Starting diagnostic sweep to isolate failing cell..."
            )
            single_sql = """
                INSERT INTO [dbo].[Table_Data_Output] (
                    [Execution_ID], [Model_ID], [Table_Data_ID], [Doc_ID],
                    [Row_Index], [FOT_Name], [Extracted_Value], [Page_Number],
                    [Review_Status],
                    [Created_Date], [Created_By]
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            diag_cursor = conn.cursor()
            for r in chunk:
                try:
                    if isinstance(r, dict):
                        diag_params = (
                            r.get("Execution_ID"),
                            r.get("Model_ID"),
                            r.get("Table_Data_ID"),
                            r.get("Doc_ID"),
                            r.get("Row_Index"),
                            r.get("FOT_Name"),
                            r.get("Extracted_Value"),
                            r.get("Page_Number"),
                            r.get("Review_Status", "Pending"),
                            r.get("Created_Date", created_date),
                            r.get("Created_By"),
                        )
                    else:
                        diag_params = r
                    diag_cursor.execute(single_sql, diag_params)
                except pyodbc.Error as cell_err:
                    conn.rollback()
                    row_idx = r.get("Row_Index") if isinstance(r, dict) else r[4]
                    fot_name = r.get("FOT_Name") if isinstance(r, dict) else r[5]
                    extracted_val = r.get("Extracted_Value") if isinstance(r, dict) else r[6]
                    page_num = r.get("Page_Number") if isinstance(r, dict) else r[7]
                    logger.error(
                        f"[DB ERROR PINPOINTED] Table cell insertion failed: "
                        f"Row_Index={row_idx}, FOT_Name='{fot_name}', "
                        f"Extracted_Value='{extracted_val}', Page_Number={page_num}. Reason: {cell_err}"
                    )
                    raise cell_err
            raise batch_err

    if commit:
        conn.commit()

    logger.info(f"[DB] Insert_Table_Data_Output_Batch → Successfully inserted {len(inserted_ids)} cells.")
    return inserted_ids


def Update_Table_Data_Output(
    conn: pyodbc.Connection,
    Table_Output_ID: int,
    Updated_By: str,
    Review_Status: Optional[str] = None,
    Reviewed_By: Optional[str] = None,
    Corrected_Value: Optional[str] = None,
    Extracted_Value: Optional[str] = None,
) -> None:
    """
    Updates review / correction fields on a table output row.
    Primarily called by the web UI after human review.

    Example:
        Update_Table_Data_Output(
            conn=conn,
            Table_Output_ID=table_output_id,
            Review_Status="Corrected",
            Reviewed_By="jane.doe",
            Corrected_Value="12500.00",
            Updated_By="AgenticCR_WebApp",
        )
    """
    sql = """
        UPDATE [dbo].[Table_Data_Output]
        SET
            [Review_Status]   = COALESCE(?, [Review_Status]),
            [Reviewed_By]     = COALESCE(?, [Reviewed_By]),
            [Corrected_Value] = COALESCE(?, [Corrected_Value]),
            [Extracted_Value] = COALESCE(?, [Extracted_Value]),
            [Updated_Date]    = ?,
            [Updated_By]      = ?
        WHERE [Table_Output_ID] = ?
    """
    params = (
        Review_Status, Reviewed_By, Corrected_Value, Extracted_Value,
        _now(), Updated_By,
        Table_Output_ID,
    )
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        logger.info(f"[DB] Update_Table_Data_Output → Table_Output_ID={Table_Output_ID}")
    except pyodbc.Error as e:
        conn.rollback()
        logger.error(f"[DB] Update_Table_Data_Output failed: {e}")
        raise


# ===========================================================================
# API READ OPERATIONS
# ===========================================================================

def Get_Execution_Status(conn: pyodbc.Connection, execution_id: int) -> Optional[dict]:
    """
    Queries Execution_Master for the given execution_id.
    """
    sql = """
        SELECT [Execution_Status], [Remarks], [Start_Time], [End_Time], [Model_ID]
        FROM [dbo].[Execution_Master]
        WHERE [Execution_ID] = ?
    """
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (execution_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "Execution_Status": row[0],
            "Remarks": row[1],
            "Start_Time": row[2].isoformat() if row[2] else None,
            "End_Time": row[3].isoformat() if row[3] else None,
            "Model_ID": row[4]
        }
    except pyodbc.Error as e:
        logger.error(f"[DB] Get_Execution_Status failed: {e}")
        raise


def Get_Execution_Audits(conn: pyodbc.Connection, execution_id: int) -> list:
    """
    Queries Execution_Audit table for rows matching the execution_id.
    """
    sql = """
        SELECT [Stage], [Stage_Status], [Stage_Start], [Stage_End], [Remark]
        FROM [dbo].[Execution_Audit]
        WHERE [Execution_ID] = ?
        ORDER BY [Created_Date] ASC
    """
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (execution_id,))
        rows = cursor.fetchall()
        audits = []
        for row in rows:
            audits.append({
                "Stage": row[0],
                "Stage_Status": row[1],
                "Stage_Start": row[2].isoformat() if row[2] else None,
                "Stage_End": row[3].isoformat() if row[3] else None,
                "Remark": row[4]
            })
        return audits
    except pyodbc.Error as e:
        logger.error(f"[DB] Get_Execution_Audits failed: {e}")
        raise


def Get_Document_Status(conn: pyodbc.Connection, execution_id: int) -> list:
    """
    Queries Document_Table for rows matching the execution_id.
    """
    sql = """
        SELECT [Doc_ID], [File_Name], [Doc_Status], [Tokens_used], [Input_Tokens], [Output_Tokens]
        FROM [dbo].[Document_Table]
        WHERE [Execution_ID] = ?
    """
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (execution_id,))
        rows = cursor.fetchall()
        docs = []
        for row in rows:
            docs.append({
                "Doc_ID": row[0],
                "File_Name": row[1],
                "Doc_Status": row[2],
                "Tokens_used": row[3],
                "Input_Tokens": row[4],
                "Output_Tokens": row[5]
            })
        return docs
    except pyodbc.Error as e:
        logger.error(f"[DB] Get_Document_Status failed: {e}")
        raise


def Get_Document_Result(conn: pyodbc.Connection, execution_id: int) -> Optional[str]:
    """
    Queries Document_Table to retrieve the extracted Json_Output for the given execution_id.
    """
    sql = """
        SELECT [Json_Output]
        FROM [dbo].[Document_Table]
        WHERE [Execution_ID] = ?
    """
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (execution_id,))
        row = cursor.fetchone()
        return row[0] if row else None
    except pyodbc.Error as e:
        logger.error(f"[DB] Get_Document_Result failed: {e}")
        raise

def get_llm_config(conn: pyodbc.Connection, llm_config_id: int = None) -> tuple:
    """
    Retrieves the LLM Provider, API Key, Model Name, and Base URL from the LLM_Config table.
    If llm_config_id is provided, fetches that specific active config.
    Otherwise, defaults to the first active configuration.
    Returns (provider, api_key, model_name, base_url).
    """
    if llm_config_id is not None:
        sql = """
            SELECT [LLM_Provider], [API_Key], [Model_Name], [Base_URL]
            FROM [dbo].[LLM_Config]
            WHERE [Status] = 1 AND [LLM_Config_ID] = ?
        """
        params = (llm_config_id,)
    else:
        sql = """
            SELECT TOP 1 [LLM_Provider], [API_Key], [Model_Name], [Base_URL]
            FROM [dbo].[LLM_Config]
            WHERE [Status] = 1
        """
        params = ()

    try:
        cursor = conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
            
        row = cursor.fetchone()
        if row:
            provider = row[0] or "openai"
            return provider, row[1], row[2], row[3]
        else:
            raise ValueError(f"No active LLM configuration found (Requested ID: {llm_config_id}).")
    except pyodbc.Error as e:
        logger.error(f"[DB] get_llm_config failed: {e}")
        raise

def get_ocr_config(conn: pyodbc.Connection) -> tuple:
    """
    Retrieves the OCR Provider, API Key, and Base URL from the OCR_Config table.
    Assumes there is an active configuration (Status = 1).
    Returns (ocr_provider, api_key, base_url).
    """
    sql = """
        SELECT TOP 1 [OCR_Provider], [API_Key], [Base_URL]
        FROM [dbo].[OCR_Config]
        WHERE [Status] = 1
    """
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        row = cursor.fetchone()
        if row:
            return row[0], row[1], row[2]
        else:
            raise ValueError("No active OCR configuration found in OCR_Config table.")
    except pyodbc.Error as e:
        logger.error(f"[DB] get_ocr_config failed: {e}")
        raise
