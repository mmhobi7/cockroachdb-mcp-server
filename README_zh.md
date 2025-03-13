# CockroachDB MCP 服务器

[English](README.md) | [简体中文](README_zh.md)

这是一个用于 Cursor 的 CockroachDB MCP 服务器，基于 Model Context Protocol (MCP) 规范实现，可以让你在 Cursor 中直接与 CockroachDB 数据库交互。

## 功能

- 连接到 CockroachDB 数据库
- 获取数据库中的所有表
- 获取表的结构信息
- 执行 SQL 查询
- 提供数据库状态资源
- 提供 SQL 查询提示模板
- 自动重连机制，确保连接稳定性
- 连接保活机制，防止连接超时
- 优雅的进程退出处理
- 详细的日志记录，便于故障排除
- 支持手动断开连接

## 安装

1. 克隆仓库并进入项目目录
2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 安装 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 在 Cursor 中使用

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

## MCP 功能说明

### 工具 (Tools)

#### connect_database

连接到 CockroachDB 数据库。

参数：
- `jdbc_url`: JDBC 连接 URL (例如: jdbc:postgresql://localhost:26257/defaultdb)
- `username`: 数据库用户名
- `password`: 数据库密码

#### initialize_connection

初始化数据库连接，可以在连接到 MCP 服务器后立即调用此工具来建立数据库连接。

参数：
- `jdbc_url`: JDBC 连接 URL (例如: jdbc:postgresql://localhost:26257/defaultdb)
- `username`: 数据库用户名
- `password`: 数据库密码

#### disconnect_database

手动断开与数据库的连接。

无参数。

#### get_tables

获取数据库中的所有表。

无参数。

#### get_table_schema

获取指定表的结构信息。

参数：
- `table_name`: 表名

#### execute_query

执行 SQL 查询。

参数：
- `query`: SQL 查询语句

### 资源 (Resources)

#### db://status

获取数据库连接状态。

返回：
- 未连接时：`"未连接"`
- 已连接时：`"已连接 - [数据库版本]"`
- 连接错误时：`"连接错误 - [错误信息]"`

### 提示模板 (Prompts)

#### sql_query_template

SQL 查询提示模板，用于帮助用户编写 SQL 查询。

## 日志

服务器日志保存在 `logs/cockroachdb_mcp.log` 文件中。你可以通过查看这个文件来了解服务器的运行状态和详细日志。

日志文件使用循环日志机制，每个日志文件最大 10MB，最多保留 5 个备份文件，以防止日志占用过多磁盘空间。

## 特殊字符处理

本服务器使用 psycopg2 直接连接到 CockroachDB 数据库，它会自动处理用户名和密码中的特殊字符，无需额外的 URL 编码。这确保了即使密码中包含特殊字符（如 `@`、`%`、`&` 等），也能正确连接到数据库。

## TCP 保活设置

服务器默认配置了 TCP 保活机制，以防止连接因为长时间不活动而被关闭：

- `keepalives=1`：启用 TCP keepalive
- `keepalives_idle=30`：空闲 30 秒后发送 keepalive
- `keepalives_interval=10`：每 10 秒发送一次 keepalive
- `keepalives_count=5`：5 次尝试后放弃

## 故障排除

如果遇到问题，请查看日志文件 `logs/cockroachdb_mcp.log`，这将帮助你了解服务器的运行状态和可能出现的问题。

### 常见问题

1. **连接被拒绝**：确保 CockroachDB 服务器正在运行，并且可以从你的机器访问。
2. **认证失败**：检查用户名和密码是否正确。
3. **连接超时**：检查网络连接是否稳定，特别是当连接到远程数据库时。
4. **数据库服务器问题**：检查 CockroachDB 服务器是否正常运行。