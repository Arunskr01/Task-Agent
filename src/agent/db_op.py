import logging
import os
import pyodbc
from typing import Optional

logger = logging.getLogger(__name__)

def get_db_connection(
    server: str,
    database: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    trusted_connection: bool = False,
) -> pyodbc.Connection:
    
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
