# paper-map — Map Agent

Map Agent 将 Reader 的 `paper-card.json` 转成可追溯的跨论文知识状态。它先比较具体 knowledge units 的问题、构念、分析单位、情境和证据模式，再裁定关系；不会依据主题相似、引用边或 embedding 自动接受关系。

## 输入

```text
papers/**/paper-card.json
searches/**/research-record.md      # provisional hints
papers/**/research-record.md        # 仅在 card 不足时定向回查
```

## 输出

```text
knowledge/relations.jsonl
knowledge/map.json
knowledge/MAP.md
knowledge/INDEX.md
knowledge-vault/
```

## 关系

```text
supports / extends / conditions / challenges /
conflicts / measurement / incomparable
```

`conflicts` 只允许用于充分可比的端点；结果方向不同并不自动构成冲突。

## 命令

```bash
python3 paper-map/map.py init --root .
python3 paper-map/map.py validate --root .
python3 paper-map/map.py candidates --root . --paper P51 --limit 8
python3 paper-map/map.py render --root .
python3 -m unittest discover -s paper-map/tests -v
```

脚本使用 Python 3 标准库。`candidates` 只召回局部邻居，Map Agent 仍需阅读两个 cards、执行可比性门并人工写入 relation。`render` 不覆盖 `knowledge-vault/90-Human-Notes/`。
