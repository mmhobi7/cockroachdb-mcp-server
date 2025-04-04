import os
import logging
from logging.handlers import RotatingFileHandler
import sys
import json
import psycopg2
import psycopg2.extras
import traceback
import signal
from typing import Dict, List, Any
from urllib.parse import urlparse
from mcp.server.fastmcp import FastMCP

# Create logs directory (if it doesn't exist)
os.makedirs('logs', exist_ok=True)

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set to DEBUG level for more information

# Create a RotatingFileHandler, max 10MB per log file, keep up to 5 backups
file_handler = RotatingFileHandler('logs/cockroachdb_mcp.log', maxBytes=10*1024*1024, backupCount=5)
file_handler.setLevel(logging.DEBUG)

# Create a formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Add handler to the logger
logger.addHandler(file_handler)

# Add console log handler for easy debugging
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Global variables
db_connection = None
last_connect_params = None  # Store the last used connection parameters

def signal_handler(sig, frame):
    """Handle process signals to ensure graceful exit"""
    logger.info(f"Received signal {sig}, preparing to exit")
    global db_connection
    
    # Close database connection
    if db_connection:
        try:
            db_connection.close()
            logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error closing database connection: {str(e)}")
    
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Initialize FastMCP server
mcp = FastMCP(
    "cockroachdb-mcp",
    description="CockroachDB MCP server for interacting directly with CockroachDB database in Cursor",
    version="1.0.0"
)

def parse_jdbc_url(jdbc_url):
    """Parse JDBC URL and return connection parameters using urllib"""
    # Remove "jdbc:" prefix if present
    if jdbc_url.startswith("jdbc:"):
        jdbc_url = jdbc_url[5:]

    parsed = urlparse(jdbc_url)

    # Extract components
    host = parsed.hostname
    port = parsed.port if parsed.port else 26257  # Default CockroachDB port
    database = parsed.path.lstrip('/') if parsed.path else "defaultdb" # Remove leading slash

    # Extract query parameters
    query_params = {}
    if parsed.query:
        for param in parsed.query.split("&"):
            if "=" in param:
                key, value = param.split("=", 1)
                query_params[key] = value

    # Note: username and password are handled separately by the connect_database function
    # This parser focuses on host, port, database, and query params from the URL itself.

    return host, port, database, query_params

def create_connection(host, port, database, username, password, query_params):
    """Create database connection"""
    # Build connection parameters
    connect_params = {
        "host": host,
        "port": port,
        "user": username,
        "password": password,
        "database": database,
        "sslmode": "require",
        "application_name": "cockroachdb-mcp",
        "keepalives": 1,              # Enable TCP keepalive
        "keepalives_idle": 30,        # Send keepalive after 30 seconds of idle time
        "keepalives_interval": 10,    # Send keepalive every 10 seconds
        "keepalives_count": 5         # Give up after 5 attempts
    }
    
    # Add query parameters
    if "TimeZone" in query_params:
        connect_params["options"] = f"-c timezone={query_params['TimeZone']}"
    
    # Connect directly using psycopg2
    logger.info(f"Connection parameters: {json.dumps({k: v for k, v in connect_params.items() if k != 'password'})}")
    
    # Create connection
    conn = psycopg2.connect(**connect_params)
    conn.set_session(autocommit=True)  # Set autocommit
    return conn, connect_params

@mcp.tool()
async def connect_database(jdbc_url: str, username: str, password: str) -> str:
    """Connect to CockroachDB database.
    
    Args:
        jdbc_url: JDBC connection URL (e.g., jdbc:postgresql://localhost:26257/defaultdb)
        username: Database username
        password: Database password
    """
    global db_connection, last_connect_params
    try:
        logger.info(f"Attempting to connect to database: {jdbc_url}")
        
        # Parse JDBC URL
        host, port, database, query_params = parse_jdbc_url(jdbc_url)
        
        # If connection exists, close it first
        if db_connection:
            try:
                db_connection.close()
                # logger.info("Closed existing database connection.")
            except Exception as close_exc:
                pass
                # logger.warning(f"Error closing existing database connection: {close_exc}")
                # Continue even if closing failed

        # Create new connection
        db_connection, last_connect_params = create_connection(host, port, database, username, password, query_params)
        
        # Test connection
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        
        logger.info("Database connection successful")
        return "Database connection successful"
    except Exception as e:
        error_msg = f"Database connection failed: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return error_msg

@mcp.tool()
async def disconnect_database() -> str:
    """Disconnect from the database.
    
    Returns:
        Result of disconnection
    """
    global db_connection
    
    logger.info("Disconnecting database connection")
    
    # Close database connection
    if db_connection:
        try:
            db_connection.close()
            db_connection = None
            logger.info("Database connection closed")
            return "Database connection closed"
        except Exception as e:
            error_msg = f"Error closing database connection: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return error_msg
    else:
        return "No active database connection currently"

def _ensure_connection():
    """Checks for an active DB connection and attempts reconnection if necessary."""
    global db_connection, last_connect_params
    if db_connection:
        # Check if the connection is still alive
        try:
            with db_connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            return # Connection is good
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            # logger.warning(f"Connection check failed: {e}. Attempting reconnect.")
            db_connection = None # Force reconnect attempt below

    if not db_connection:
        if last_connect_params:
            # logger.info("No active connection or connection lost. Attempting to reconnect...")
            try:
                db_connection = psycopg2.connect(**last_connect_params)
                db_connection.set_session(autocommit=True)
                # logger.info("Database reconnection successful.")
            except Exception as e:
                logger.error(f"Failed to reconnect to database: {str(e)}")
                db_connection = None # Ensure connection is None if reconnect fails
                raise ConnectionError(f"Failed to reconnect to database: {str(e)}") # Raise specific error
        else:
            logger.error("Not connected to database and no previous connection parameters found.")
            raise ConnectionError("Not connected to database and no previous connection parameters found.")

@mcp.tool()
async def get_tables() -> Dict[str, List[Dict[str, str]]]:
    """Get all tables from the database.
    
    Returns:
        Dictionary containing table information
    """
    global db_connection # last_connect_params is handled by _ensure_connection

    try:
        _ensure_connection() # Ensure connection is active

        with db_connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            # Get all tables
            cursor.execute("""
                SELECT 
                    table_schema,
                    table_name,
                    table_type
                FROM 
                    information_schema.tables 
                WHERE 
                    table_schema NOT IN ('pg_catalog', 'information_schema', 'crdb_internal')
                    AND table_type = 'BASE TABLE'
                ORDER BY 
                    table_schema, 
                    table_name
            """)
            tables = cursor.fetchall()
            
            # Get column information for each table
            result = []
            for table in tables:
                cursor.execute("""
                    SELECT 
                        column_name,
                        data_type,
                        character_maximum_length,
                        column_default,
                        is_nullable
                    FROM 
                        information_schema.columns
                    WHERE 
                        table_schema = %s 
                        AND table_name = %s
                    ORDER BY 
                        ordinal_position
                """, (table['table_schema'], table['table_name']))
                columns = cursor.fetchall()
                
                table_info = {
                    'schema': table['table_schema'],
                    'name': table['table_name'],
                    'type': table['table_type'],
                    'columns': columns
                }
                result.append(table_info)
            
            return {"tables": result}
    except Exception as e:
        error_msg = f"Failed to get table information: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        
        # If a connection error occurs *during* the query, log it but don't retry here.
        # _ensure_connection handles the initial check/reconnect attempt.
        if isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError)):
             logger.error("Connection error occurred during query execution.")
             # Optionally reset db_connection to None to force reconnect on next call
             # db_connection = None

        return {"error": error_msg}

@mcp.tool()
async def get_table_schema(table_name: str) -> Dict[str, List[Dict[str, str]]]:
    """Get structure information of a specified table.
    
    Args:
        table_name: Table name
        
    Returns:
        Dictionary containing table structure information
    """
    global db_connection # last_connect_params is handled by _ensure_connection

    try:
        _ensure_connection() # Ensure connection is active

        with db_connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            # Parse table_name for schema.table format
            if '.' in table_name:
                schema_name, table_name_only = table_name.split('.', 1)
            else:
                schema_name = 'public' # Default to public schema if not specified
                table_name_only = table_name

            logger.info(f"Getting schema for table: {table_name_only} in schema: {schema_name}")

            # Get table column information
            cursor.execute("""
                SELECT
                    column_name,
                    data_type,
                    character_maximum_length,
                    column_default,
                    is_nullable
                FROM
                    information_schema.columns
                WHERE
                    table_schema = %s AND table_name = %s
                ORDER BY
                    ordinal_position
            """, (schema_name, table_name_only))
            columns = cursor.fetchall()
            
            if not columns:
                return {"error": f"Table '{table_name_only}' in schema '{schema_name}' does not exist or no columns found."}
            
            # Get table index information
            cursor.execute("""
                SELECT 
                    i.relname as index_name,
                    a.attname as column_name,
                    ix.indisunique as is_unique,
                    ix.indisprimary as is_primary
                FROM 
                    pg_class t,
                    pg_class i,
                    pg_index ix,
                    pg_attribute a
                WHERE 
                    t.oid = ix.indrelid
                    AND i.oid = ix.indexrelid
                    AND a.attrelid = t.oid
                    AND a.attnum = ANY(ix.indkey)
                    AND t.relkind = 'r'
                    AND t.relname = %s
                    AND n.nspname = %s -- Filter by schema name
                FROM
                    pg_class t
                    JOIN pg_index ix ON t.oid = ix.indrelid
                    JOIN pg_class i ON i.oid = ix.indexrelid
                    JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
                    JOIN pg_namespace n ON t.relnamespace = n.oid -- Join with namespace for schema name
                WHERE
                    t.relkind = 'r'
                    AND t.relname = %s -- table name
                    AND n.nspname = %s -- schema name
                ORDER BY
                    i.relname
            """, (table_name_only, schema_name))
            indexes = cursor.fetchall()
            
            return {
                "columns": columns,
                "indexes": indexes
            }
    except Exception as e:
        error_msg = f"Failed to get table structure: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        
        # If a connection error occurs *during* the query, log it but don't retry here.
        if isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError)):
             logger.error("Connection error occurred during query execution.")
             # db_connection = None # Optionally reset

        return {"error": error_msg}

@mcp.tool()
async def execute_query(query: str) -> Dict[str, Any]:
    """Execute SQL query.
    
    Args:
        query: SQL query statement
        
    Returns:
        Query results or number of affected rows
    """
    global db_connection # last_connect_params is handled by _ensure_connection

    try:
        _ensure_connection() # Ensure connection is active

        with db_connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(query)
            
            # If it's a SELECT query, return the result set
            if query.strip().upper().startswith("SELECT"):
                results = cursor.fetchall()
                return {"results": results}
            # Otherwise, return the number of affected rows
            else:
                return {"affected_rows": cursor.rowcount}
    except Exception as e:
        error_msg = f"Failed to execute query: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        
        # If a connection error occurs *during* the query, log it but don't retry here.
        if isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError)):
             logger.error("Connection error occurred during query execution.")
             # db_connection = None # Optionally reset

        return {"error": error_msg}

@mcp.resource("db://status")
async def get_db_status() -> str:
    """Get database connection status"""
    global db_connection # last_connect_params is handled by _ensure_connection
    try:
        _ensure_connection() # Ensure connection is active
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            status = f"Connected - {version}"
            logger.info(f"Getting database status: {status}")
            return status
    except Exception as e:
        status = f"Connection error - {str(e)}"
        logger.error(f"Failed to get database status: {status}")
        logger.error(traceback.format_exc())
        # If the error is a DB connection issue after _ensure_connection passed,
        # it might indicate the connection dropped again. Resetting might be wise.
        if isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError)):
            db_connection = None # Reset connection state
        return status
    except ConnectionError as ce: # Catch specific error from _ensure_connection
        status = f"Connection error - {str(ce)}"
        logger.error(f"Failed to get database status: {status}")
        return status
    except Exception as e: # Catch other errors during SELECT version()
        status = f"Error checking status - {str(e)}"
        logger.error(f"Failed to get database status: {status}")
        logger.error(traceback.format_exc())
        # If the error is a DB connection issue after _ensure_connection passed,
        # it might indicate the connection dropped again. Resetting might be wise.
        if isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError)):
            db_connection = None
        return status

@mcp.prompt("sql_query_template")
async def sql_query_template() -> str:
    """SQL query prompt template"""
    logger.info("Getting SQL query prompt template")
    return """
    -- Query example
    SELECT * FROM table_name WHERE condition;
    
    -- Insert example
    INSERT INTO table_name (column1, column2) VALUES (value1, value2);
    
    -- Update example
    UPDATE table_name SET column1 = value1 WHERE condition;
    
    -- Delete example
    DELETE FROM table_name WHERE condition;
    """

# Removed redundant initialize_connection tool. Use connect_database instead.

if __name__ == "__main__":
    logger.info("Starting CockroachDB MCP server...")
    try:
        # Run the server
        mcp.run(transport='stdio')
        logger.info("Server started successfully")
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        logger.error(traceback.format_exc()) 