# 墨笺前端

基于 React、TypeScript、Vite 和 React Router 的小说创作工作台。

## 本地开发

先在项目根目录启动 FastAPI：

```powershell
python -m uvicorn main:app --reload
```

再启动前端：

```powershell
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173`。开发服务器会把 `/api` 请求代理到 `http://127.0.0.1:8000`。

## 生产构建

```powershell
npm run build
```

构建产物位于 `frontend/dist/`。

## 前端测试

```powershell
npm test
```

## 章节管理与回收站

在“我的作品”卡片中展开“管理章节”，可以将单章移入回收站。回收站分为“作品”和“章节”两个标签页，支持搜索、还原和二次确认后的彻底删除；章节删除/还原会更新作品的章节数，还原时保留原章节编号。

还原作品不会同时还原此前单独删除的章节。若所属作品也在回收站，先还原作品，再还原章节。彻底删除作品会一并删除全部章节，此操作不可恢复。

后端回收站路由集中在 `routers/recycle_bin.py`，业务在 `crud/recycle_bin.py`，前端调用统一的 `/api/recycle-bin` 接口；原项目回收站 URL 仍兼容，但已标记为弃用。

后端启动时会检查旧表，并按需补充 `project.previous_status`、回收站状态和 `chapters.is_deleted`（已有章节默认未删除）。数据库账号需要具有相应的 ALTER 权限；启动前建议备份数据库。
