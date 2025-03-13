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
from mcp.server.fastmcp import FastMCP

# 创建logs目录（如果不存在）
os.makedirs('logs', exist_ok=True)

# 配置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # 设置为DEBUG级别以获取更多信息

# 创建一个RotatingFileHandler，每个日志文件最大10MB，最多保留5个备份
file_handler = RotatingFileHandler('logs/cockroachdb_mcp.log', maxBytes=10*1024*1024, backupCount=5)
file_handler.setLevel(logging.DEBUG)

# 创建一个格式化器
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# 将处理器添加到日志记录器
logger.addHandler(file_handler)

# 添加控制台日志处理器，方便调试
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# 全局变量
db_connection = None
last_connect_params = None  # 存储最后一次使用的连接参数

def signal_handler(sig, frame):
    """处理进程信号，确保优雅退出"""
    logger.info(f"收到信号 {sig}，准备退出")
    global db_connection
    
    # 关闭数据库连接
    if db_connection:
        try:
            db_connection.close()
            logger.info("数据库连接已关闭")
        except Exception as e:
            logger.error(f"关闭数据库连接时出错: {str(e)}")
    
    sys.exit(0)

# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# 初始化FastMCP服务器
mcp = FastMCP(
    "cockroachdb-mcp",
    description="CockroachDB MCP 服务器，用于在 Cursor 中直接与 CockroachDB 数据库交互",
    version="1.0.0"
)

def parse_jdbc_url(jdbc_url):
    """解析JDBC URL并返回连接参数"""
    # 格式: jdbc:postgresql://host:port/database?param1=value1&param2=value2
    jdbc_url = jdbc_url.replace("jdbc:", "")
    
    # 分离查询参数
    url_parts = jdbc_url.split("?")
    base_url = url_parts[0]
    query_params = {}
    if len(url_parts) > 1:
        query_string = url_parts[1]
        for param in query_string.split("&"):
            if "=" in param:
                key, value = param.split("=", 1)
                query_params[key] = value
    
    # 解析基本URL部分
    base_url = base_url.replace("postgresql://", "")
    host_port_db = base_url.split("/")
    host_port = host_port_db[0].split(":")
    host = host_port[0]
    port = int(host_port[1]) if len(host_port) > 1 else 26257
    database = host_port_db[1] if len(host_port_db) > 1 else "defaultdb"
    
    return host, port, database, query_params

def create_connection(host, port, database, username, password, query_params):
    """创建数据库连接"""
    # 构建连接参数
    connect_params = {
        "host": host,
        "port": port,
        "user": username,
        "password": password,
        "database": database,
        "sslmode": "require",
        "application_name": "cockroachdb-mcp",
        "keepalives": 1,              # 启用TCP keepalive
        "keepalives_idle": 30,        # 空闲30秒后发送keepalive
        "keepalives_interval": 10,    # 每10秒发送一次keepalive
        "keepalives_count": 5         # 5次尝试后放弃
    }
    
    # 添加查询参数
    if "TimeZone" in query_params:
        connect_params["options"] = f"-c timezone={query_params['TimeZone']}"
    
    # 使用psycopg2直接连接
    logger.info(f"连接参数: {json.dumps({k: v for k, v in connect_params.items() if k != 'password'})}")
    
    # 创建连接
    conn = psycopg2.connect(**connect_params)
    conn.set_session(autocommit=True)  # 设置自动提交
    return conn, connect_params

@mcp.tool()
async def connect_database(jdbc_url: str, username: str, password: str) -> str:
    """连接到CockroachDB数据库。
    
    Args:
        jdbc_url: JDBC连接URL (例如: jdbc:postgresql://localhost:26257/defaultdb)
        username: 数据库用户名
        password: 数据库密码
    """
    global db_connection, last_connect_params
    try:
        logger.info(f"尝试连接数据库: {jdbc_url}")
        
        # 解析JDBC URL
        host, port, database, query_params = parse_jdbc_url(jdbc_url)
        
        # 如果已有连接，先关闭
        if db_connection:
            try:
                db_connection.close()
            except:
                pass
        
        # 创建新连接
        db_connection, last_connect_params = create_connection(host, port, database, username, password, query_params)
        
        # 测试连接
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        
        logger.info("数据库连接成功")
        return "数据库连接成功"
    except Exception as e:
        error_msg = f"数据库连接失败: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return error_msg

@mcp.tool()
async def disconnect_database() -> str:
    """断开与数据库的连接。
    
    Returns:
        断开连接的结果
    """
    global db_connection
    
    logger.info("断开数据库连接")
    
    # 关闭数据库连接
    if db_connection:
        try:
            db_connection.close()
            db_connection = None
            logger.info("数据库连接已关闭")
            return "数据库连接已关闭"
        except Exception as e:
            error_msg = f"关闭数据库连接时出错: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return error_msg
    else:
        return "当前没有活跃的数据库连接"

@mcp.tool()
async def get_tables() -> Dict[str, List[Dict[str, str]]]:
    """获取数据库中的所有表。
    
    Returns:
        包含表信息的字典
    """
    global db_connection, last_connect_params
    if not db_connection:
        try:
            if last_connect_params:
                logger.info("尝试重新连接数据库")
                db_connection = psycopg2.connect(**last_connect_params)
                db_connection.set_session(autocommit=True)
            else:
                error_msg = "未连接到数据库"
                logger.error(error_msg)
                return {"error": error_msg}
        except Exception as e:
            error_msg = f"重新连接数据库失败: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}

    try:
        with db_connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            # 获取所有表
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
            
            # 获取每个表的列信息
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
        error_msg = f"获取表信息失败: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        
        # 如果是连接错误，尝试重新连接
        if isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError)):
            try:
                if last_connect_params:
                    logger.info("尝试重新连接数据库")
                    db_connection = psycopg2.connect(**last_connect_params)
                    db_connection.set_session(autocommit=True)
                    return await get_tables()
            except Exception as reconnect_error:
                logger.error(f"重新连接失败: {str(reconnect_error)}")
        
        return {"error": error_msg}

@mcp.tool()
async def get_table_schema(table_name: str) -> Dict[str, List[Dict[str, str]]]:
    """获取指定表的结构信息。
    
    Args:
        table_name: 表名
        
    Returns:
        包含表结构信息的字典
    """
    global db_connection, last_connect_params
    if not db_connection:
        try:
            if last_connect_params:
                logger.info("尝试重新连接数据库")
                db_connection = psycopg2.connect(**last_connect_params)
                db_connection.set_session(autocommit=True)
            else:
                error_msg = "未连接到数据库"
                logger.error(error_msg)
                return {"error": error_msg}
        except Exception as e:
            error_msg = f"重新连接数据库失败: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}

    try:
        with db_connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            # 获取表的列信息
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
                    table_name = %s
                ORDER BY 
                    ordinal_position
            """, (table_name,))
            columns = cursor.fetchall()
            
            if not columns:
                return {"error": f"表 {table_name} 不存在"}
            
            # 获取表的索引信息
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
                ORDER BY 
                    i.relname
            """, (table_name,))
            indexes = cursor.fetchall()
            
            return {
                "columns": columns,
                "indexes": indexes
            }
    except Exception as e:
        error_msg = f"获取表结构失败: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        
        # 如果是连接错误，尝试重新连接
        if isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError)):
            try:
                if last_connect_params:
                    logger.info("尝试重新连接数据库")
                    db_connection = psycopg2.connect(**last_connect_params)
                    db_connection.set_session(autocommit=True)
                    return await get_table_schema(table_name)
            except Exception as reconnect_error:
                logger.error(f"重新连接失败: {str(reconnect_error)}")
        
        return {"error": error_msg}

@mcp.tool()
async def execute_query(query: str) -> Dict[str, Any]:
    """执行SQL查询。
    
    Args:
        query: SQL查询语句
        
    Returns:
        查询结果或影响的行数
    """
    global db_connection, last_connect_params
    if not db_connection:
        try:
            if last_connect_params:
                logger.info("尝试重新连接数据库")
                db_connection = psycopg2.connect(**last_connect_params)
                db_connection.set_session(autocommit=True)
            else:
                error_msg = "未连接到数据库"
                logger.error(error_msg)
                return {"error": error_msg}
        except Exception as e:
            error_msg = f"重新连接数据库失败: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}

    try:
        with db_connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(query)
            
            # 如果是SELECT查询，返回结果集
            if query.strip().upper().startswith("SELECT"):
                results = cursor.fetchall()
                return {"results": results}
            # 否则返回受影响的行数
            else:
                return {"affected_rows": cursor.rowcount}
    except Exception as e:
        error_msg = f"执行查询失败: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        
        # 如果是连接错误，尝试重新连接
        if isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError)):
            try:
                if last_connect_params:
                    logger.info("尝试重新连接数据库")
                    db_connection = psycopg2.connect(**last_connect_params)
                    db_connection.set_session(autocommit=True)
                    return await execute_query(query)
            except Exception as reconnect_error:
                logger.error(f"重新连接失败: {str(reconnect_error)}")
        
        return {"error": error_msg}

@mcp.resource("db://status")
async def get_db_status() -> str:
    """获取数据库连接状态"""
    global db_connection, last_connect_params
    if not db_connection:
        logger.info("获取数据库状态: 未连接")
        return "未连接"
    
    try:
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            status = f"已连接 - {version}"
            logger.info(f"获取数据库状态: {status}")
            return status
    except Exception as e:
        status = f"连接错误 - {str(e)}"
        logger.error(f"获取数据库状态失败: {status}")
        logger.error(traceback.format_exc())
        
        # 尝试重新连接
        if last_connect_params:
            try:
                logger.info("尝试重新连接数据库")
                db_connection = psycopg2.connect(**last_connect_params)
                db_connection.set_session(autocommit=True)
                logger.info("数据库重新连接成功")
                
                with db_connection.cursor() as cursor:
                    cursor.execute("SELECT version()")
                    version = cursor.fetchone()[0]
                    status = f"已连接 - {version}"
                    logger.info(f"获取数据库状态: {status}")
                    return status
            except Exception as reconnect_error:
                logger.error(f"数据库重新连接失败: {str(reconnect_error)}")
        
        return status

@mcp.prompt("sql_query_template")
async def sql_query_template() -> str:
    """SQL查询提示模板"""
    logger.info("获取SQL查询提示模板")
    return """
    -- 查询示例
    SELECT * FROM table_name WHERE condition;
    
    -- 插入示例
    INSERT INTO table_name (column1, column2) VALUES (value1, value2);
    
    -- 更新示例
    UPDATE table_name SET column1 = value1 WHERE condition;
    
    -- 删除示例
    DELETE FROM table_name WHERE condition;
    """

# 添加一个初始化连接的工具，用于替代@mcp.init
@mcp.tool()
async def initialize_connection(jdbc_url: str, username: str, password: str) -> str:
    """初始化连接，当客户端连接时调用。
    
    Args:
        jdbc_url: JDBC连接URL (例如: jdbc:postgresql://localhost:26257/defaultdb)
        username: 数据库用户名
        password: 数据库密码
        
    Returns:
        初始化结果
    """
    global db_connection, last_connect_params
    try:
        logger.info(f"尝试初始化数据库连接: {jdbc_url}")
        
        # 解析JDBC URL
        host, port, database, query_params = parse_jdbc_url(jdbc_url)
        
        # 如果已有连接，先关闭
        if db_connection:
            try:
                db_connection.close()
            except:
                pass
        
        # 创建新连接
        db_connection, last_connect_params = create_connection(host, port, database, username, password, query_params)
        
        # 测试连接
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        
        logger.info("数据库连接初始化成功")
        return "数据库连接初始化成功"
    except Exception as e:
        error_msg = f"数据库连接初始化失败: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return error_msg

if __name__ == "__main__":
    logger.info("Starting CockroachDB MCP server...")
    try:
        # 运行服务器
        mcp.run(transport='stdio')
        logger.info("Server started successfully")
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        logger.error(traceback.format_exc()) 