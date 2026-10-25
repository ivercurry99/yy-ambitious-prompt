# yy-ambitious-prompt

把普通提示词改写成结果导向、专家级、带外部验证的野心版。按高度（任务→结果）、深度（专家工具与原始数据）、广度（名词换动词、跨行业借方法）三个维度诊断并改写，附带一个离线诊断脚本。

[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![CI](https://github.com/ivercurry99/yy-ambitious-prompt/actions/workflows/ci.yml/badge.svg)](https://github.com/ivercurry99/yy-ambitious-prompt/actions/workflows/ci.yml)
![Platform](https://img.shields.io/badge/platform-win%20%7C%20mac%20%7C%20linux-lightgrey)

## 它解决什么问题

大多数人给 AI 的指令停留在任务级：「帮我修这个报错」「把数据填进 PPT」「请你扮演一个资深投资人」。第三种尤其常见——模型只换了说话腔调，干活的方法一点没变。

本技能把一段提示词按三个维度诊断后改写：

| 维度 | 改写前 | 改写后 |
|---|---|---|
| 高度 | 帮我修一下这个报错 | 保证上传功能连续 7 天成功率不低于 99.5%，从服务端日志原始记录入手定位 |
| 深度 | 请你扮演资深投资人分析这家公司 | 连接真实财务数据库，交叉比对三年现金流，找出可疑关联交易；结论由独立脚本复核 |
| 广度 | 做一份季度业务回顾 PPT | 让管理层更早发现渠道问题：设计一套比季度 PPT 更早预警的机制，用历史数据证明预警提前量 |

三条硬规则贯穿所有改写：禁止角色扮演式写法（必须换成专家的工具、数据和方法）、必含外部验证条款（真实测试、独立脚本，不让模型自评自审）、不编造用户没给的信息。

方法论整理自 Anthropic 工程师 Felix 的文章《How to Be More Ambitious》。

## 离线诊断脚本

不调用模型也能先给提示词打个分。8 个检测器（7 个问题检测 + 1 个结果级信号），纯 Python 标准库，零依赖：

```bash
python scripts/audit.py diagnose --file examples/sample-prompt.txt
```

```text
提示词野心度诊断
长度: 44 字
总分: 30/100    高度: 85/100    深度: 45/100    广度: 需模型判断（静态脚本不评）
发现:
[high][depth] roleplay
  证据: 扮演
[medium][altitude] task_verb
  证据: 帮我、整理
[low][altitude] format_purpose
  证据: 汇报、PPT
[high][depth] no_verification
[low][depth] no_raw_data
[medium][depth] vague_goal
  证据: 尽量、更好
```

三条命令：

| 命令 | 用途 |
|---|---|
| `diagnose` | 完整诊断，支持位置参数 / `--file` / 管道，`--json` 输出结构化结果 |
| `validate --min-score N` | 分数门槛门禁，供 CI 使用，达标 exit 0 |
| `capabilities` | 列出全部检测器及其严重级别 |

`range`（广度）字段恒为 `null`：跨行业借喻是语义判断，正则匹配只会产生假精度，该维度由调用方模型判断。

## 作为技能使用

把仓库克隆到你的技能目录（以 Trae 为例）：

```bash
git clone https://github.com/ivercurry99/yy-ambitious-prompt.git
cp -r yy-ambitious-prompt ~/.trae-cn/skills/
```

或用 skills CLI 安装：

```bash
npx skills add ivercurry99/yy-ambitious-prompt
```

安装后对 AI 说「优化提示词」「改写提示词」「让提示词更有野心」，并附上你的原始需求，即可触发。技能会按四段式输出：诊断（三维度评级 + 原文证据）→ 改写后的提示词（可直接复制）→ 关键改动（标注维度）→ 遗留确认（最多 2 条）。

完整的改写案例、四问自助模板、反模式清单见 [references/](references/) 目录。

## 与其他方案的区别

| | 本技能 | 清晰度改写类技能 | 独立优化器应用 |
|---|---|---|---|
| 定位 | 把提示词抬到结果级、专家级、跨行业 | 把模糊提示词改清晰 | 独立服务，需要模型 API |
| 诊断框架 | 高度 / 深度评分 + 广度声明不可静态评 | 清晰度、完整性 | 自动化迭代优化 |
| 反角色扮演硬规则 | 有（写入 SKILL.md 强制条款） | 不做要求 | 不做要求 |
| 外部验证条款 | 强制包含 | 不做要求 | 视实现 |
| 离线脚本 | 有，纯标准库 | 视项目 | 无（依赖在线模型） |
| 测试与 CI | 46 个用例，覆盖率 98.6%，CI 强制 85% | 视项目 | 视项目 |

## 开发

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ --cov=scripts --cov-fail-under=85
```

## 许可证

MIT，见 [LICENSE](LICENSE)。
