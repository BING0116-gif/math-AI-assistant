# T15 学生对照验证协议

本目录用于验证动画是否比 T08 静态图更有助于理解变化过程。它只收集匿名、最小化的实验数据，
不得填写姓名、学号、邮箱、聊天记录或原始题目照片。

## 设计

- 目标学生：8–12 人。
- 概念：割线趋近切线、Riemann 和、Taylor 逼近。
- 每名参与者对三个概念分别完成静态图和动画条件，共六次；条件顺序交叉随机化。
- 每次展示后回答一道等难度解释题，记录是否正确和完成秒数。
- 动画条件额外记录 1–5 分帮助度，以及是否出现眩晕、分心或移动端播放问题。
- `participant_id` 只能使用本次实验生成的随机代号，不得关联真实身份。

先复制 `responses-template.csv`，再录入数据：

```powershell
Copy-Item ops/math_animator_poc/student_validation/responses-template.csv `
  artifacts/t15-phase0/student-validation-responses.csv
```

分析命令：

```powershell
.\venv\Scripts\python.exe `
  ops/math_animator_poc/student_validation/analyze.py `
  artifacts/t15-phase0/student-validation-responses.csv
```

## 门禁

数据完整且满足以下全部条件时，教学价值门禁才通过：

1. 至少 8 名参与者均完成三个概念的静态和动画条件；
2. 动画解释题正确率至少提高 10 个百分点，或动画完成时间中位数至少降低 15% 且正确率不下降；
3. 至少 70% 的动画记录帮助度为 4 或 5；
4. 严重不良反馈为 0，普通不良反馈比例不超过 20%。

脚本只输出聚合结果。原始 CSV 放在被忽略的 `artifacts/` 中，不提交到 Git。

