# 评论员智能体离线评测

`review_dataset.json` 是不调用真实模型的固定回归样本，覆盖：

- 同一稿件重复评审的评分漂移；
- 评审建议的采纳、部分采纳和拒绝；
- 修订前后评分提升。

运行评测：

```powershell
python -m services.review_evaluation
```

默认评分漂移容忍度为 5 分。评测失败会返回非零退出码，适合接入提交检查。
