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
