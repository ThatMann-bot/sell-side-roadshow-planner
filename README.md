# Sell-side Roadshow Planner

卖方路演行程规划 skill：面向卖方研究员、销售、IR 和投研团队，把零散的买方拜访信息整理成可执行的同城/单日路演行程。

它适合处理这类输入：

```text
周三北京5家，机构A 9点张总、机构B下午2点李总、机构C王总灵活、机构D赵总灵活、机构E陈总4点半
```

## What It Does

- 从微信式短消息、截图 OCR、语音转写或表格中提取机构、联系人、时间、固定/灵活约束。
- 用高德/地图 API 查询机构地址候选，并把地图候选与官网地址分开呈现。
- 对官网、联系我们页面或披露地址做核验，避免直接相信截图、样例地址或旧地址。
- 区分固定会议、灵活会议、时间窗口、起点、终点、午饭、缓冲和体力约束。
- 使用高德单段路线估算，枚举全日拜访顺序，给出全局路径规划和备选路线。
- 根据效率优先、体力优先、全程打车、地铁优先、高跟鞋/正装/行李/下雨等状态选择交通策略。
- 在行程变动时，重新排程并生成可直接发给销售或买方的中文沟通话术。

## How It Works

The skill follows this workflow:

1. Normalize messy meeting text into structured meetings.
2. Look up live map address candidates with `scripts/address_lookup.py`.
3. Cross-check likely official addresses with `scripts/official_address_check.py`.
4. Ask the user to confirm ambiguous or recently moved offices.
5. Build a schedule model with fixed anchors and flexible windows.
6. Optimize the route with `scripts/amap_route_optimizer.py` when there are three or more stops or when route optimality matters.
7. Produce a copyable itinerary, route rationale, risk notes, and change messages.

Important distinction:

> Amap/Gaode provides single-leg route estimates. This skill performs whole-day meeting-order optimization on top of those estimates.

## Installation

Agent skills are installed by giving your AI agent access to a folder that contains `SKILL.md` at its root. Most users do not need to clone this repository with Git.

Recommended generic flow:

1. Open this repository on GitHub.
2. Click **Code** -> **Download ZIP**.
3. Unzip it.
4. Make sure the final folder is named `sell-side-roadshow-planner` and contains `SKILL.md`, `scripts/`, `references/`, and `agents/`.
5. Copy or import that folder into your agent's skills location.
6. Restart or refresh the agent if it does not detect the skill immediately.

The folder should look like this after installation:

```text
sell-side-roadshow-planner/
  SKILL.md
  agents/openai.yaml
  references/
  scripts/
```

### Codex

Install as a personal Codex skill:

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force ".\sell-side-roadshow-planner" "$env:USERPROFILE\.codex\skills\sell-side-roadshow-planner"
```

macOS/Linux:

```bash
mkdir -p ~/.codex/skills
cp -R ./sell-side-roadshow-planner ~/.codex/skills/sell-side-roadshow-planner
```

Restart Codex after copying the folder, then invoke it naturally:

```text
$sell-side-roadshow-planner 周三北京5家，机构A 9点张总、机构B下午2点李总、机构C王总灵活
```

### WorkBuddy

WorkBuddy versions may expose skills through the app UI rather than a fixed public filesystem path.

Recommended:

1. Open WorkBuddy.
2. Go to **Skills**, **Skill Marketplace**, or **Custom Skill**.
3. Choose **Import**, **Create custom skill**, or the equivalent option in your version.
4. Import the `sell-side-roadshow-planner` folder, or paste the contents of `SKILL.md` and attach the `scripts/` and `references/` folders as supporting resources.
5. Refresh/restart WorkBuddy if the skill does not appear immediately.

If your WorkBuddy build supports local skill folders, place the whole folder under the local skills directory used by your client, commonly:

```text
~/.agents/skills/sell-side-roadshow-planner/
```

On Windows, that is usually:

```text
C:\Users\<you>\.agents\skills\sell-side-roadshow-planner\
```

Keep the folder structure intact; do not copy only `SKILL.md`, because the skill uses bundled Python scripts.

### Claude

For Claude Code, install either as a personal skill or a project skill.

Personal skill, available across projects:

```bash
mkdir -p ~/.claude/skills
cp -R ./sell-side-roadshow-planner ~/.claude/skills/sell-side-roadshow-planner
```

Project skill, available only in one repository:

```bash
mkdir -p .claude/skills
cp -R ./sell-side-roadshow-planner .claude/skills/sell-side-roadshow-planner
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills" | Out-Null
Copy-Item -Recurse -Force ".\sell-side-roadshow-planner" "$env:USERPROFILE\.claude\skills\sell-side-roadshow-planner"
```

In Claude Code, invoke it directly with:

```text
/sell-side-roadshow-planner
```

or let Claude load it automatically when your request matches the description.

For Claude.ai chat, enable code execution/file creation and upload or add the custom skill through **Customize -> Skills** if your plan supports custom skills.

### Optional: Git for Maintainers

If you want to contribute changes or keep a local working copy connected to GitHub, then cloning is useful:

```bash
git clone https://github.com/ThatMann-bot/sell-side-roadshow-planner.git
```

For regular installation, downloading the ZIP and copying/importing the folder is usually simpler.

## Map API Setup

For live address lookup and route optimization, configure at least one map provider key.

Recommended: Amap/Gaode Web Service API key.

Windows PowerShell:

```powershell
setx AMAP_KEY "your_amap_web_service_key"
```

macOS/Linux:

```bash
export AMAP_KEY="your_amap_web_service_key"
```

Supported environment variables:

- `AMAP_KEY` or `AMAP_API_KEY` for Amap/Gaode
- `BAIDU_MAP_AK` for Baidu Maps fallback address lookup
- `TENCENT_MAP_KEY` or `QQ_MAP_KEY` for Tencent Maps fallback address lookup

Without a map API key, the skill can still help structure the meeting list and ask for missing addresses, but it should not pretend to have verified addresses or current travel times.

## Usage

In Codex, invoke the skill naturally:

```text
$sell-side-roadshow-planner 周三北京5家，机构A 9点张总、机构B下午2点李总、机构C王总灵活、机构D赵总灵活、机构E陈总4点半
```

Add preferences and constraints when they matter:

```text
$sell-side-roadshow-planner 周三北京3家，机构A出发：机构B下午2点李总、机构C赵总灵活、机构D陈总4点半，穿高跟鞋、正装，体力优先
```

You can also ask follow-up questions:

```text
这个路线有做最优规划吗？
交通时间是从哪里得来的？
机构C改到上午10点，重新排一下，并给销售一段微信话术
```

## Script Utilities

Address lookup:

```bash
python scripts/address_lookup.py --city 北京 机构A 机构B 机构C --format markdown
```

Official address check:

```bash
python scripts/official_address_check.py --url https://example.com/contact --candidate "北京市..."
```

Route optimization with Amap leg estimates:

```bash
python scripts/amap_route_optimizer.py input.json --pre-buffer 10 --post-buffer 5 --pre-fixed-buffer 15 --preference energy --format markdown
```

Offline scheduling from a user-supplied travel-time matrix:

```bash
python scripts/roadshow_scheduler.py input.json --pre-buffer 10 --post-buffer 5 --pre-fixed-buffer 15 --preference hybrid
```

All bundled Python scripts use the Python standard library only.

## Output Style

A typical answer includes:

- address candidates and official-site cross-check status
- chronological itinerary
- transport mode and estimated travel time for each leg
- fixed/flexible status and buffers
- lunch/rest/energy notes
- route rationale and optimization evidence
- open confirmations
- internal sales notice or buy-side message when a schedule changes

## Safety Notes

- Treat map API results as candidates, not truth.
- Do not use copied sample addresses, screenshot addresses, or stale notes as route-planning evidence.
- Cross-check official pages for address-critical institutions.
- Ask the user or sales to confirm ambiguous entities, multiple offices, recently moved headquarters, building entrance, and reception floor.
- Do not describe a whole-day order as "Amap recommended" unless Amap itself produced that exact itinerary. Use: "Amap provided single-leg estimates; the skill optimized the whole-day order."
