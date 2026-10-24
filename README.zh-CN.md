# dsh-bettercode

给 coding agent 用的 skill。它让模型在写代码前后走一套固定流程：先定数据结构再写循环，
函数短而平，性能先测量再谈优化，交付前过一遍清单。

语言无关。写新代码、重构遗留代码、代码审查都能用。

[English](README.md)

## 为什么写这个

模型能写出跑得起来的代码。它跳过的是枯燥那部分：在临时方案上再打一个补丁、
在"能跑"的循环里埋一个 O(n^2)、第一版草稿没过边界情况就交出去。

这个 skill 把这套判断换成能检查的规则。"函数不超过 40 行"可以验证，"写干净点"不能。

## 工作流程

先选路线，三条之一：

| 路线 | 走什么 |
|---|---|
| 写新代码 | Phase 1 到 5 |
| 重构遗留代码 | 重构纪律，再走 Phase 2 到 5 |
| 审查代码 | Phase 5 清单加 `references/code-smells.md`，不改代码 |

| Phase | 做什么 |
|---|---|
| 1. 动手前 | 契约、数据规模 N、是否热路径、延迟还是吞吐，据此定复杂度预算 |
| 2. 设计 | 先选数据结构，分层，纯核心加 IO 推到边缘 |
| 3. 编写 | 硬规则：早返回、一函数一职责、第三次重复必抽象、零死代码、零魔法值、禁止布尔陷阱、错误显式 |
| 4. 性能 | "永远做"清单（不变量外提、循环前建索引、IO 批量）对比微观优化，后者必须有 profile |
| 5. 交付前 | 10 条清单，不过关就改，改完再过 |

重构模式额外要求：用特征测试锁住行为，保留 legacy 怪癖并标注，用差分对拍证明等价，
坏掉的公开签名冻结后用薄适配层兜住，而不是直接改。

两份手册按需加载，不到需要时不占上下文：

| 文件 | 什么时候读 |
|---|---|
| `references/performance-patterns.md` | 做性能设计、优化、排查慢代码时。数据结构选择表、热路径流程、IO 内存并发模式、12 组反模式与处方、测量方法、各语言速记 |
| `references/code-smells.md` | 审查、重构、或踩到红线时。20 类坏味道按症状病因处方组织，附重构安全守则 |

## 安装

先 clone，再把目录复制到你的 host 找 skill 的位置。

```bash
git clone https://github.com/AkitoLane/dsh-bettercode.git
```

### DeepSeek Harness (DSH)

用户级，自动发现，不用重启：

```bash
mkdir -p ~/.dsh/skills
cp -r dsh-bettercode ~/.dsh/skills/
```

或者项目级：

```bash
mkdir -p <project>/.dsh/skills
cp -r dsh-bettercode <project>/.dsh/skills/
```

### Claude Code

```bash
mkdir -p ~/.claude/skills
cp -r dsh-bettercode ~/.claude/skills/
```

重启会话，确认它能出现在你的 skills 列表里。

### Cursor、Codex CLI、Gemini CLI、opencode

这几个 host 读的是一个普通的说明文件，不是 skill 目录。把文件夹放在项目里或项目旁边，
再让那个文件指过来。

| Host | 读哪个文件 |
|---|---|
| Cursor | `AGENTS.md` 或 `.cursor/rules/dsh-bettercode.mdc` |
| Codex CLI | `AGENTS.md`（仓库根目录或 `~/.codex/`） |
| Gemini CLI | `GEMINI.md` |
| opencode | `AGENTS.md` |

往里加一行：

```markdown
任何写码任务都先读 ./dsh-bettercode/SKILL.md，它让你加载 references/ 下的文件时再加载。
```

把 `SKILL.md` 整段贴进去也能用，但两份手册就够不着了，Phase 3 和 4 会少掉速查表。

### 确认装上了

问一个应该踩到闸门的问题：

```
用 dsh-bettercode 审一下这段代码
```

装上了的话，它会跑 Phase 5 清单，并且能说出 `code-smells.md` 里的 smell 名字。
如果回答是那种泛泛的建议，就是没加载。

## 用法

自动：description 覆盖了编写、重构、审查、优化，兼容的 host 会自己加载。

手动：`用 dsh-bettercode 重构这个模块。`

## 效果

同一个模型，带 skill 和不带，三个任务。完整数字和跑出这些数字的工具在
[EVALUATION.md](EVALUATION.md) 和 `evaluation/` 里。

- 重构 147 行上帝函数（埋了 20 处坏味道）：两组都通过 400 组差分对拍，行为可证明一致。
  skill 组消除约 19.5/20，基线 17/20；主编排函数 47 行，基线 80 行；基线放弃的布尔陷阱
  skill 组修掉了。
- 审查同一份文件（26 处埋雷）：召回 26/26，基线 24/26；性能条目 9 条对 7 条。
- 从零写滑动窗口限流器：两组都选了 deque，AST 质量分都是 100/100。规格清晰的新写任务上，
  基线本来就不差。

所以它不负责把差输出变好。它负责让上限变成可预期的东西，不取决于模型当天状态。

## 目录结构

```
SKILL.md                            skill 正文
references/performance-patterns.md  性能手册
references/code-smells.md           坏味道目录与重构守则
EVALUATION.md                       A/B 评测报告
evaluation/                         打分工具、任务题面、六份运行产物
```

## 许可证

MIT
