# 验证与人工复核

第三阶段增加人工复核模板和验证报告，目的是让自动分析结果可以被审计、抽样检查和写入论文方法限制。

## 自动生成文件

pipeline 成功完成后会在输出目录中生成：

- `06_review/source_country_review.xlsx`
- `06_review/modifier_semantic_review.xlsx`
- `07_reports/validation_report.xlsx`
- `07_reports/method_summary.md`
- `07_reports/method_limitations.md`

也可以单独运行：

```powershell
python tools/generate_validation_artifacts.py output --sample-size 50
```

## 复核字段

| 字段 | 含义 |
|---|---|
| `auto_result` | 工具自动输出的结果。 |
| `human_result` | 人工修正或确认后的结果。 |
| `is_correct` | `1` 表示正确，`0` 表示错误，空白表示未复核。 |
| `error_type` | 错误类型，如 `country_error`、`extraction_error`、`polarity_error`。 |
| `notes` | 复核说明、上下文证据或修正理由。 |

## 验证报告

`validation_report.xlsx` 会汇总已填写 `is_correct` 的复核结果。如果复核表还没有填写，报告中的 Reviewed 为 0，Accuracy 留空。

## 写作建议

论文中应明确说明：自动输出用于定位候选语言模式，最终解释依赖 KWIC 上下文阅读和人工复核。国别识别、修饰语提取和语义韵候选都应作为辅助证据，而不是无误差事实。
