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

Clone this repository into your Codex skills directory.

Windows PowerShell:

```powershell
git clone https://github.com/ThatMann-bot/sell-side-roadshow-planner.git "$env:USERPROFILE\.codex\skills\sell-side-roadshow-planner"
```

macOS/Linux:

```bash
git clone https://github.com/ThatMann-bot/sell-side-roadshow-planner.git ~/.codex/skills/sell-side-roadshow-planner
```

Restart Codex after installation so the new skill can be discovered.

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

