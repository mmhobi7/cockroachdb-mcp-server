# CockroachDB MCP Server

[English](README.md) | [简体中文](README_zh.md)

This is a CockroachDB MCP server for Cursor, implemented based on the Model Context Protocol (MCP) specification, allowing you to interact directly with CockroachDB database in Cursor.

## Features

- Connect to CockroachDB database
- Get all tables from the database
- Get table structure information
- Execute SQL queries
- Provide database status resources
- Provide SQL query templates
- Automatic reconnection mechanism to ensure connection stability
- Connection keep-alive mechanism to prevent connection timeout
- Graceful process exit handling
- Detailed logging for troubleshooting
- Support manual disconnection

## Installation

1. Clone the repository and enter the project directory
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Using in Cursor

```json
{
    "mcpServers": {
        "cockroachdb-mcp": {
            "command": "uv",
            "args": [
                "--directory",
                "/Users/local/cockroachdb-mcp",
                "run",
                "server.py"
            ],
            "jdbc_url": "jdbc:postgresql://localhost:26257/defaultdb",
            "username": "root",
            "password": "root"
        }
    }
  }
```

## MCP Function Description

### Tools

#### connect_database

Connect to CockroachDB database.

Parameters:
- `jdbc_url`: JDBC connection URL (e.g., jdbc:postgresql://localhost:26257/defaultdb)
- `username`: Database username
- `password`: Database password

#### initialize_connection

Initialize database connection, can be called immediately after connecting to the MCP server to establish a database connection.

Parameters:
- `jdbc_url`: JDBC connection URL (e.g., jdbc:postgresql://localhost:26257/defaultdb)
- `username`: Database username
- `password`: Database password

#### disconnect_database

Manually disconnect from the database.

No parameters.

#### get_tables

Get all tables from the database.

No parameters.

#### get_table_schema

Get structure information of a specified table.

Parameters:
- `table_name`: Table name

#### execute_query

Execute SQL query.

Parameters:
- `query`: SQL query statement

### Resources

#### db://status

Get database connection status.

Returns:
- When not connected: `"Not connected"`
- When connected: `"Connected - [Database version]"`
- When connection error: `"Connection error - [Error message]"`

### Prompts

#### sql_query_template

SQL query template to help users write SQL queries.

## Logs

Server logs are saved in `logs/cockroachdb_mcp.log` file. You can check this file to understand the server's running status and detailed logs.

The log file uses a rotating log mechanism, with each log file maximum size of 10MB and keeping up to 5 backup files to prevent excessive disk space usage.

## Special Character Handling

This server uses psycopg2 to connect directly to CockroachDB database, which automatically handles special characters in usernames and passwords without additional URL encoding. This ensures correct database connection even when passwords contain special characters (such as `@`, `%`, `&`, etc.).

## TCP Keep-alive Settings

The server is configured with TCP keep-alive mechanism by default to prevent connections from being closed due to long periods of inactivity:

- `keepalives=1`: Enable TCP keepalive
- `keepalives_idle=30`: Send keepalive after 30 seconds of idle time
- `keepalives_interval=10`: Send keepalive every 10 seconds
- `keepalives_count=5`: Give up after 5 attempts

## Troubleshooting

If you encounter problems, please check the log file `logs/cockroachdb_mcp.log`, which will help you understand the server's running status and potential issues.

### Common Issues

1. **Connection Refused**: Ensure the CockroachDB server is running and accessible from your machine.
2. **Authentication Failed**: Check if the username and password are correct.
3. **Connection Timeout**: Check if the network connection is stable, especially when connecting to a remote database.
4. **Database Server Issues**: Check if the CockroachDB server is running properly. 