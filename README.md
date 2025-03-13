# CockroachDB MCP 服务器

这是一个用于 Cursor 的 CockroachDB MCP 服务器，基于 [Model Context Protocol (MCP)](https://github.com/modelcontextprotocol/python-sdk) 规范实现，可以让你在 Cursor 中直接与 CockroachDB 数据库交互。

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

1. 克隆仓库：

```bash
git clone https://github.com/yourusername/cockroachdb-mcp.git
cd cockroachdb-mcp
```

2. 安装依赖：

```bash
pip install -r requirements.txt
```

## 配置

在 Cursor 中，添加以下配置到 `.vscode/settings.json` 文件：

```json
{
    "mcpServers": {
        "cockroachdb-mcp": {
            "command": "python",
            "args": [
                "/path/to/cockroachdb-mcp/server.py"
            ],
            "connectionParameters": {
                "jdbc_url": "jdbc:postgresql://localhost:26257/defaultdb",
                "username": "root",
                "password": ""
            }
        }
    }
}
```

请根据你的 CockroachDB 配置修改连接参数。

### SSL 配置

本服务器默认使用 `sslmode=require` 参数连接到 CockroachDB，这适用于大多数 CockroachDB 部署，因为 CockroachDB 通常在安全模式下运行，要求 SSL 连接。

如果你需要修改 SSL 配置，可以修改 `server.py` 文件中的 `create_connection` 函数，将 `sslmode='require'` 替换为以下选项之一：

- `sslmode='disable'`：禁用 SSL 连接（仅适用于非安全模式的 CockroachDB）
- `sslmode='verify-ca'`：要求 SSL 连接并验证服务器证书
- `sslmode='verify-full'`：要求 SSL 连接，验证服务器证书和主机名

例如：
```python
connect_params = {
    "host": host,
    "port": port,
    "user": username,
    "password": password,
    "database": database,
    "sslmode": "disable",
    "application_name": "cockroachdb-mcp",
    # ... 其他参数
}
```

### 特殊字符处理

本服务器使用 psycopg2 直接连接到 CockroachDB 数据库，它会自动处理用户名和密码中的特殊字符，无需额外的 URL 编码。这确保了即使密码中包含特殊字符（如 `@`、`%`、`&` 等），也能正确连接到数据库。

### TCP 保活设置

服务器默认配置了 TCP 保活机制，以防止连接因为长时间不活动而被关闭：

- `keepalives=1`：启用 TCP keepalive
- `keepalives_idle=30`：空闲 30 秒后发送 keepalive
- `keepalives_interval=10`：每 10 秒发送一次 keepalive
- `keepalives_count=5`：5 次尝试后放弃

如果你的网络环境需要不同的设置，可以在 `create_connection` 函数中修改这些参数。

## 使用方法

### 在 Cursor 中使用

1. 打开 Cursor
2. 使用 `Ctrl+Shift+P` 打开命令面板
3. 输入 `MCP: Connect to Server`
4. 选择 `cockroachdb-mcp`
5. 现在你可以在 Cursor 中使用 CockroachDB 相关的工具了

### 测试服务器

你可以使用提供的模拟器脚本来测试服务器：

```bash
python cursor_simulator.py
```

这将模拟 Cursor 与 MCP 服务器的交互过程。

### 测试数据库连接

你可以使用提供的测试脚本来验证数据库连接是否正常：

```bash
python test_connection.py [jdbc_url] [username] [password]
```

如果不提供参数，脚本将使用默认值。这个脚本会尝试连接到数据库，并显示连接参数和结果，帮助你诊断连接问题。

## 日志

服务器日志保存在 `logs/cockroachdb_mcp.log` 文件中。你可以通过查看这个文件来了解服务器的运行状态和详细日志。

日志文件使用循环日志机制，每个日志文件最大 10MB，最多保留 5 个备份文件，以防止日志占用过多磁盘空间。

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

## 高级功能

### 自动连接

虽然服务器不会自动连接到数据库，但你可以在连接到 MCP 服务器后立即调用 `initialize_connection` 工具来建立数据库连接。这样用户无需手动调用 `connect_database` 工具即可开始使用。

### 自动重连机制

服务器实现了自动重连机制，当检测到数据库连接断开时，会自动尝试重新连接。这在以下情况下特别有用：

- 数据库服务器临时不可用
- 网络连接暂时中断
- 数据库连接因为长时间不活动而被关闭

重连机制在以下函数中实现：
- `get_tables`
- `get_table_schema`
- `execute_query`
- `get_db_status`

### 连接保活线程

服务器启动了一个后台线程，每 30 秒执行一次简单的查询（`SELECT 1`），以保持数据库连接活跃。这可以防止连接因为长时间不活动而被数据库服务器或网络设备关闭。

如果保活查询失败，线程会尝试重新连接数据库。

### 信号处理

服务器注册了 SIGINT 和 SIGTERM 信号处理器，确保在收到这些信号时能够优雅地关闭数据库连接和后台线程，防止资源泄漏。

## 版本兼容性

本服务器使用 MCP SDK 与最新版本的 Cursor 兼容。服务器使用标准的 MCP 工具、资源和提示模板 API，不依赖于特定版本的 SDK 特性。

## 故障排除

如果遇到问题，请查看日志文件 `logs/cockroachdb_mcp.log`，这将帮助你了解服务器的运行状态和可能出现的问题。

### 常见问题

1. **SSL 连接错误**：如果遇到 SSL 相关的连接错误，请尝试修改 `create_connection` 函数中的 `sslmode` 参数。
2. **连接被拒绝**：确保 CockroachDB 服务器正在运行，并且可以从你的机器访问。
3. **认证失败**：检查用户名和密码是否正确。
4. **版本解析错误**：如果遇到 "Could not determine version from string" 错误，这通常是因为 SQLAlchemy 无法正确解析 CockroachDB 的版本字符串。我们已经切换到使用 psycopg2 直接连接，这应该解决了这个问题。
5. **AttributeError: 'FastMCP' object has no attribute 'init'**：如果遇到这个错误，说明你的 MCP SDK 版本不支持 `init` 装饰器。最新版本的代码已经移除了对这个装饰器的依赖，改用标准的工具函数 `initialize_connection`。

### "Client closed" 错误详细排除指南

如果遇到 "client closed" 错误，可能是由于以下原因：

#### 1. 连接超时

**症状**：在长时间不活动后，尝试执行查询时出现 "client closed" 错误。

**解决方案**：
- 最新版本的服务器已添加连接保活机制，每 30 秒执行一次查询以保持连接活跃。
- 确保你使用的是最新版本的服务器代码。
- 如果问题仍然存在，可以尝试减少保活间隔时间，在 `keep_connection_alive` 函数中修改 `keep_alive_event.wait(30)` 为更短的时间，例如 `keep_alive_event.wait(15)`。

#### 2. JDBC URL 参数问题

**症状**：连接初始化成功，但在执行查询时出现 "client closed" 错误。

**解决方案**：
- 确保 JDBC URL 格式正确，特别是当包含查询参数时。
- 尝试简化 JDBC URL，移除不必要的参数，例如：
  ```json
  "jdbc_url": "jdbc:postgresql://172.22.37.86:26257/bjwa_ys"
  ```
- 使用 `test_connection.py` 脚本测试连接，查看详细的连接参数和错误信息。

#### 3. 网络问题

**症状**：连接间歇性失败，或者在网络波动后出现 "client closed" 错误。

**解决方案**：
- 检查网络连接是否稳定，特别是当连接到远程数据库时。
- 如果使用 VPN 或代理，确保它们正常工作。
- 尝试增加 TCP keepalive 参数的值，使连接更加稳定：
  ```python
  "keepalives_idle": 15,        # 减少空闲时间
  "keepalives_interval": 5,     # 减少间隔时间
  "keepalives_count": 10        # 增加尝试次数
  ```

#### 4. 服务器崩溃

**症状**：服务器突然停止响应，日志中可能有错误信息。

**解决方案**：
- 检查日志文件 `logs/cockroachdb_mcp.log`，查找可能的错误原因。
- 确保服务器有足够的系统资源（内存、CPU）。
- 如果服务器因为未处理的异常而崩溃，最新版本已经增强了错误处理，应该能够捕获大多数异常。

#### 5. 数据库服务器问题

**症状**：连接初始化成功，但在执行查询时出现错误，或者数据库服务器拒绝连接。

**解决方案**：
- 检查 CockroachDB 服务器是否正常运行。
- 查看 CockroachDB 服务器日志，了解可能的连接问题。
- 确保数据库用户有足够的权限执行查询。
- 检查数据库服务器的连接限制和超时设置。

### 高级故障排除步骤

如果以上步骤都不能解决问题，请尝试以下高级故障排除方法：

1. **启用详细日志**：服务器已经配置为使用 DEBUG 级别的日志，这应该能够提供足够的信息来诊断问题。

2. **使用网络分析工具**：使用 `tcpdump` 或 Wireshark 等工具分析网络流量，查看连接是否正常建立和维护。

3. **检查系统资源**：使用 `top`、`htop` 或任务管理器监控系统资源使用情况，确保没有资源瓶颈。

4. **检查防火墙设置**：确保防火墙没有阻止与数据库服务器的连接，特别是长时间空闲的连接。

5. **检查数据库连接池设置**：如果数据库服务器配置了连接池，确保它不会过早地关闭空闲连接。

6. **使用数据库监控工具**：使用 CockroachDB 提供的监控工具查看连接状态和查询执行情况。

## 参考资料

- [Model Context Protocol (MCP) Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [CockroachDB 文档](https://www.cockroachlabs.com/docs/)
- [psycopg2 文档](https://www.psycopg.org/docs/)
- [PostgreSQL 连接参数](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING)
- [TCP Keepalive 参数说明](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-KEEPALIVES)

## 许可证

MIT
