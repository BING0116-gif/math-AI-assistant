# Task 2.1 黄金评测集

## 目录

- `manifest.yaml`：版本化注册层，声明来源 `evaluations/model_quality/v2`、七类能力、最小样本量和每类评分契约。
- `schema/golden_case.schema.json`：展开后单样例的 JSON Schema。
- `reports/report-template.md`：离线/真实运行报告模板。
- `privacy.yaml`：去敏规则与发布前检查清单。

注册层只保存现有 v2 case ID 和类别元数据，不复制题目、图片或模型结果。扩展时先在来源评测集新增并完成其审核，再更新本注册层版本与哈希。

## 最小样本量

每类至少 5 个样例（共至少 35 个注册样例；同一来源样例可在不同能力维度复用）。正式发布前应逐类补充正常、歧义/噪声、错误但貌似合理和拒答边界样例。

## 校验

```powershell
python scripts/validate_golden_eval.py
python scripts/validate_golden_eval.py --json
```

校验器不调用模型，不读取生产数据库；失败返回非零。它会校验来源 v2 的 hash、case ID、类别选择、最小样本量、七个必填字段和隐私禁用字段。

## 去敏策略

只接受合成输入或已完成许可审查的公开素材；禁止真实姓名、联系方式、学号、账号、令牌、生产日志和可回溯用户标识。图片必须去除 EXIF/上传元数据并以 SHA-256 固定。报告只记录 case ID、版本、评分和脱敏错误摘要，不记录原始学生输入或密钥。
