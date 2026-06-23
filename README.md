# 卖方路演行程规划

这是一个面向卖方研究员、销售、IR 和投研团队的路演行程规划技能。它可以把零散的买方拜访信息整理成可执行的同城/单日路演行程，并在地址、路线、体力、午饭和沟通话术之间做平衡。

它适合处理这类输入：

```text
周三北京5家，机构A 9点张总、机构B下午2点李总、机构C王总灵活、机构D赵总灵活、机构E陈总4点半
```

## 能做什么

- 从微信式短消息、截图 OCR、语音转写或表格中提取机构、联系人、时间、固定/灵活约束。
- 用高德/地图 API 查询机构地址候选，并把地图候选与官网地址分开呈现。
- 对官网、联系我们页面或披露地址做核验，避免直接相信截图、样例地址或旧地址。
- 区分固定会议、灵活会议、时间窗口、起点、终点、午饭、缓冲和体力约束。
- 使用高德单段路线估算，枚举全日拜访顺序，给出全局路径规划和备选路线。
- 根据效率优先、体力优先、全程打车、地铁优先、高跟鞋/正装/行李/下雨等状态选择交通策略。
- 在行程变动时，重新排程并生成可直接发给销售或买方的中文沟通话术。

## 工作方式

技能会按下面的流程工作：

1. 把杂乱的会议描述标准化为结构化会议清单。
2. 用 `scripts/address_lookup.py` 查询实时地图地址候选。
3. 用 `scripts/official_address_check.py` 交叉核验可能的官网地址。
4. 对模糊主体、多办公地、近期搬迁等情况，请用户或销售确认。
5. 基于固定会议和灵活窗口建立排程模型。
6. 当行程有三站以上，或用户关心路线是否最优时，用 `scripts/amap_route_optimizer.py` 做全局路径优化。
7. 输出可直接复制的行程表、路线逻辑、风险提示和变更沟通话术。

重要边界：

> 高德提供的是单段路线和耗时估算；本技能是在这些单段估算之上，做整天会议顺序的全局优化。

## 安装

智能体技能的本质是一个包含 `SKILL.md` 的文件夹。多数用户不需要克隆仓库，只需要下载并把整个技能文件夹交给自己的 AI 智能体。

通用安装流程：

1. 打开这个 GitHub 仓库。
2. 点击 **Code（代码）** -> **Download ZIP（下载 ZIP）**。
3. 解压 ZIP。
4. 确认最终文件夹名为 `sell-side-roadshow-planner`，并且里面包含 `SKILL.md`、`scripts/`、`references/` 和 `agents/`。
5. 把整个文件夹复制或导入到你的智能体技能目录。
6. 如果智能体没有立刻识别，重启或刷新智能体。

安装后的文件夹结构应类似：

```text
sell-side-roadshow-planner/
  SKILL.md
  agents/openai.yaml
  references/
  scripts/
```

### Codex 安装

作为个人 Codex 技能安装：

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force ".\sell-side-roadshow-planner" "$env:USERPROFILE\.codex\skills\sell-side-roadshow-planner"
```

macOS/Linux：

```bash
mkdir -p ~/.codex/skills
cp -R ./sell-side-roadshow-planner ~/.codex/skills/sell-side-roadshow-planner
```

复制完成后重启 Codex，然后自然调用：

```text
$sell-side-roadshow-planner 周三北京5家，机构A 9点张总、机构B下午2点李总、机构C王总灵活
```

### WorkBuddy 安装

不同版本的 WorkBuddy 可能通过应用内界面管理技能，而不是固定读取某个公开文件夹。

推荐方式：

1. 打开 WorkBuddy。
2. 进入 **技能**、**技能市场** 或 **自定义技能**。
3. 选择 **导入**、**创建自定义技能** 或当前版本中的等价入口。
4. 导入 `sell-side-roadshow-planner` 文件夹，或粘贴 `SKILL.md` 内容，并把 `scripts/`、`references/` 作为支持资源附上。
5. 如果没有立刻出现，刷新或重启 WorkBuddy。

如果你的 WorkBuddy 版本支持本地技能文件夹，可以把整个文件夹放到客户端使用的本地技能目录，常见位置是：

```text
~/.agents/skills/sell-side-roadshow-planner/
```

Windows 上通常是：

```text
C:\Users\<you>\.agents\skills\sell-side-roadshow-planner\
```

请保持完整文件夹结构，不要只复制 `SKILL.md`，因为这个技能依赖内置 Python 脚本。

### Claude 安装

Claude Code 可以安装为个人技能，也可以安装为项目级技能。

个人技能，跨项目可用：

```bash
mkdir -p ~/.claude/skills
cp -R ./sell-side-roadshow-planner ~/.claude/skills/sell-side-roadshow-planner
```

项目级技能，只在当前仓库可用：

```bash
mkdir -p .claude/skills
cp -R ./sell-side-roadshow-planner .claude/skills/sell-side-roadshow-planner
```

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills" | Out-Null
Copy-Item -Recurse -Force ".\sell-side-roadshow-planner" "$env:USERPROFILE\.claude\skills\sell-side-roadshow-planner"
```

在 Claude Code 中可以直接调用：

```text
/sell-side-roadshow-planner
```

也可以让 Claude 在请求匹配技能描述时自动加载。

如果使用 Claude.ai 网页版，请先启用代码执行/文件创建能力，并在 **Customize（自定义）-> Skills（技能）** 中上传或添加自定义技能，前提是你的计划支持自定义技能。

### 维护者可选：使用 Git

如果你想贡献修改，或想保留一个和 GitHub 远程仓库关联的本地工作副本，再使用 Git 克隆：

```bash
git clone https://github.com/ThatMann-bot/sell-side-roadshow-planner.git
```

普通安装通常用下载 ZIP、复制文件夹或应用内导入就够了。

## 通过和 Agent 对话导入

如果你的智能体有文件访问能力，并且能从 GitHub 下载文件，你可以直接把下面的提示词发给智能体，让它帮你安装。这样通常比手动移动文件夹更方便。

适用于大多数兼容智能体技能格式的通用提示词：

```text
请从 GitHub 安装这个智能体技能：
https://github.com/ThatMann-bot/sell-side-roadshow-planner

请安装完整的 sell-side-roadshow-planner 文件夹，不要只安装 SKILL.md。
请保留 SKILL.md、scripts/、references/ 和 agents/。
安装完成后，请验证这个技能是否能被发现，并告诉我安装路径。
```

### 让 Codex 安装

在 Codex 中使用：

```text
请从 https://github.com/ThatMann-bot/sell-side-roadshow-planner 安装这个智能体技能。
请先检查仓库根目录有 SKILL.md，然后把完整的 sell-side-roadshow-planner 文件夹安装到我的 Codex 技能目录。
保留 scripts/、references/、agents/，不要只复制 SKILL.md。
安装后请验证技能是否能被发现，并告诉我安装路径。
```

如果 Codex 当前环境里有技能安装器，可以直接使用安装器；否则可以下载 ZIP，或读取仓库内容后复制到：

```text
~/.codex/skills/sell-side-roadshow-planner/
```

### 让 WorkBuddy 导入

在 WorkBuddy 中使用：

```text
帮我导入一个自定义 Skill：
https://github.com/ThatMann-bot/sell-side-roadshow-planner

请把整个 sell-side-roadshow-planner 文件夹作为一个 Skill 导入。
主说明文件是 SKILL.md，scripts/ 和 references/ 是支持资源。
如果当前版本不能直接从 GitHub 导入，请打开自定义技能/导入技能的界面，告诉我需要上传 ZIP 还是粘贴 SKILL.md。
```

WorkBuddy 不同版本的技能导入方式可能不同。有的版本使用应用内技能市场或自定义技能导入器，有的版本可能需要上传 ZIP，或从粘贴的 Markdown 文本创建技能。如果 WorkBuddy 不能直接从链接安装，请先下载这个仓库的 ZIP，再让 WorkBuddy 导入 ZIP 或文件夹。

### 让 Claude Code 安装

安装为 Claude Code 个人技能：

```text
请帮我安装这个智能体技能：
https://github.com/ThatMann-bot/sell-side-roadshow-planner

请把它安装为 Claude Code 个人技能，路径是：
~/.claude/skills/sell-side-roadshow-planner/

请复制完整文件夹，包括 SKILL.md、scripts/、references/ 和 agents/。
安装后请验证 `/sell-side-roadshow-planner` 是否可用。
```

安装为当前项目的 Claude Code 技能：

```text
请把这个智能体技能安装到当前项目：
https://github.com/ThatMann-bot/sell-side-roadshow-planner

请把完整文件夹放到：
.claude/skills/sell-side-roadshow-planner/

请保留 SKILL.md、scripts/、references/ 和 agents/。
安装后请验证 `/sell-side-roadshow-planner` 是否能在当前项目中使用。
```

### 让 Claude.ai 网页版添加

Claude.ai 通常通过应用内界面管理自定义技能，而不是直接访问本地文件系统。可以用下面的提示词让 Claude 引导你导入：

```text
我想添加这个自定义技能：
https://github.com/ThatMann-bot/sell-side-roadshow-planner

请指导我在 Claude.ai 的 Customize（自定义）-> Skills（技能）中添加它。
如果你能读取我上传的文件，请让我上传这个仓库的 ZIP。
技能根目录是包含 SKILL.md 的 sell-side-roadshow-planner 文件夹。
```

## 地图 API 配置

如果需要实时查址和路径优化，请至少配置一个地图服务密钥。

推荐使用高德 Web 服务 API 密钥。

Windows PowerShell：

```powershell
setx AMAP_KEY "your_amap_web_service_key"
```

macOS/Linux：

```bash
export AMAP_KEY="your_amap_web_service_key"
```

支持的环境变量：

- `AMAP_KEY` 或 `AMAP_API_KEY`：高德地图
- `BAIDU_MAP_AK`：百度地图地址查询备用
- `TENCENT_MAP_KEY` 或 `QQ_MAP_KEY`：腾讯地图地址查询备用

如果没有地图 API 密钥，技能仍然可以帮助整理会议清单并提示缺失地址，但不应该假装已经核验地址或获取了实时交通时间。

## 使用示例

在 Codex 中可以自然调用：

```text
$sell-side-roadshow-planner 周三北京5家，机构A 9点张总、机构B下午2点李总、机构C王总灵活、机构D赵总灵活、机构E陈总4点半
```

有偏好和约束时，可以一并写上：

```text
$sell-side-roadshow-planner 周三北京3家，机构A出发：机构B下午2点李总、机构C赵总灵活、机构D陈总4点半，穿高跟鞋、正装，体力优先
```

也可以继续追问或修改：

```text
这个路线有做最优规划吗？
交通时间是从哪里得来的？
机构C改到上午10点，重新排一下，并给销售一段微信话术
```

## 脚本工具

地址查询：

```bash
python scripts/address_lookup.py --city 北京 机构A 机构B 机构C --format markdown
```

官网地址核验：

```bash
python scripts/official_address_check.py --url https://example.com/contact --candidate "北京市..."
```

基于高德单段路线的全局路径优化：

```bash
python scripts/amap_route_optimizer.py input.json --pre-buffer 10 --post-buffer 5 --pre-fixed-buffer 15 --preference energy --format markdown
```

基于用户提供的交通耗时矩阵做离线排程：

```bash
python scripts/roadshow_scheduler.py input.json --pre-buffer 10 --post-buffer 5 --pre-fixed-buffer 15 --preference hybrid
```

所有内置 Python 脚本只使用 Python 标准库。

## 输出内容

典型输出包括：

- 地址候选和官网核验状态
- 按时间顺序排列的行程表
- 每段交通方式和预计耗时
- 固定/灵活状态和缓冲时间
- 午饭、休息、体力安排
- 路线逻辑和优化依据
- 仍需确认的问题
- 行程变动时的销售内部通知或买方沟通话术

## 安全与准确性提示

- 地图 API 结果只能当作候选，不等于事实。
- 不要把复制来的样例地址、截图地址或旧记录当作路线规划依据。
- 对地址关键的机构，应尽量交叉核验官网页面。
- 对主体模糊、多办公地、近期搬迁、楼宇入口、前台楼层等情况，应请用户或销售确认。
- 除非高德本身生成了整天行程顺序，否则不要说“这是高德推荐的整天路线”。应表述为：“高德提供单段耗时，本技能基于这些单段结果优化整天顺序。”
