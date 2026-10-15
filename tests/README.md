# 后端测试

在仓库根目录运行：

```powershell
python -B -m unittest discover -s tests -v
```

除项目运行依赖外，测试需要 `httpx` 和 `aiosqlite`：

```powershell
python -m pip install httpx aiosqlite
```

测试使用独立的 SQLite 内存数据库和模拟数据库升级，不连接开发用 MySQL，也不会修改现有项目数据。覆盖权限隔离、软删除/还原、原状态与章节编号保留、章节数统计、级联彻底删除、失败事务回滚及旧表升级。

章节回收状态独立于项目：还原项目不会自动还原此前单独删除的章节。所属项目在回收站时，章节还原返回 409，必须先还原项目；彻底删除项目则删除其所有章节，包括单独回收的章节。

测试库不模拟 MySQL 行锁；并发锁行为仍需在独立 MySQL 测试环境中验证。

## 模型接入层

`test_llm_client.py` 覆盖环境配置优先级、参数校验、同步/异步调用、流式输出、工具响应透传、错误处理与资源释放。通过 `httpx.MockTransport` 测试真实 SDK，不连接第三方模型、不消耗额度。所需依赖见 `agent/requirements.txt`。
