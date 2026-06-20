# 股海贼王系统

这是一个 A 股收盘后复盘流水线的最小可行版本。它用富途 OpenAPI 拉取股票池、快照、所属板块、历史 K 线和资金流，再生成一张每日 CSV 表，用于回答：

- 今天哪些票接近涨停？
- 今天成交额前三十是谁？
- 它们属于什么行业和概念？
- 当前阶段是首板、连板、突破、放量还是高位震荡？
- 在同题材里更像龙头、中军、先锋还是后排？

## 当前范围

已实现：

- A 股股票池获取：沪深正股基础信息。
- 涨停候选筛选：主板 10cm、创业板/科创板 20cm、ST 5cm，并预留浮点误差。
- 成交额 TopN：默认 Top30。
- 所属板块归类：行业、概念分开输出。
- 题材强度：按涨停数量、平均涨幅、成交额合计排序。
- 板块研究候选：在 HTML 报告中按涨幅强度、成交额、扩散度、涨停数量、核心个股和量比信号生成研究分。
- 市场周期：按涨停数量、上涨家数占比、全市场平均涨幅粗分上升、高潮、分歧、修复、退潮、冰点。
- 题材层级：按题材强度粗分主线、支线、轮动、退潮老题材。
- 阶段标签：首板、连板、创 20/60 日新高、放量、低位启动、平台突破、高位震荡。
- 个股地位：同题材内粗分龙头、容量核心、中军、补涨、跟风、杂毛。
- 次日计划：结合市场周期、题材层级、个股地位，生成退潮空仓、核心分歧低吸、转强确认加仓、轻仓试错、去弱留强等动作提示。
- 资金流：净流入、主力净流入字段。
- CSV 报表输出。

暂未接入公告、新闻、研报和题材原因库，所以“上涨原因”默认输出“不明”。这部分应作为第二阶段扩展。

## 运行前准备

1. 启动 Futu OpenD，默认地址为 `127.0.0.1:11111`。
2. 安装可选富途依赖：

```bash
python3 -m pip install -e ".[futu]"
```

3. 安装 AkShare，用于历史 K 线缓存兜底和次日验证：

```bash
python3 -m pip install -e ".[akshare]"
```

4. 可选安装 TuShare，用于更稳定的历史 K 线来源：

```bash
python3 -m pip install -e ".[tushare]"
```

配置 TuShare token，二选一：

```bash
export TUSHARE_TOKEN="你的token"
```

或运行命令时临时传入：

```bash
PYTHONPATH=src python3 -m ghzw.cli --tushare-token "你的token" --history-source tushare
```

TuShare 历史 K 线需要 token 具备 `daily` 接口访问权限。如果终端提示：

```text
没有接口(daily)访问权限
```

说明 token 可用，但当前账号权限不足；系统会使用本地缓存，并尝试后续兜底源。

如果只跑离线测试，不需要安装富途 SDK。

## 图形界面日常使用

项目根目录提供了一个可双击启动文件：

```text
启动股海贼王.command
```

日常使用时，双击它即可启动本地网页工作台，并自动打开浏览器。工作台支持：

- 生成每日复盘。
- 快速复盘：默认跳过历史 K 线、资金流、线上证据和论坛检索，用于快速查看涨停、成交额和板块结构。
- 生成次日验证。
- 浏览 `outputs/daily/` 下的历史报表。
- 搜索、筛选、排序和下载 CSV。

也可以用命令启动：

```bash
PYTHONPATH=src python3 -m ghzw.gui
```

如果浏览器没有自动打开，终端窗口会显示本地访问地址，例如：

```text
http://127.0.0.1:8765
```

工作台默认开启“快速复盘”，适合试用和盘后快速浏览。需要更完整的阶段标签、资金流、公告/新闻/龙虎榜证据和论坛线索时，取消勾选“快速复盘”后再生成。

## 上涨原因与复盘质量

系统会优先读取本地原因库：

```text
data/reasons/reasons.csv
```

字段为：

```text
日期,代码,原因类型,原因摘要,来源,可信度,链接,发布时间
```

示例：

```text
2026-06-14,SZ.000001,公告,拟收购资产并复牌,公司公告,高,,
```

如果本地原因库没有命中，系统会根据核心题材、阶段、资金流等生成“疑似”原因，例如：

```text
疑似：人工智能主线发酵，个股涨停
```

带有“疑似”的原因只是规则推断，不等同于公告、新闻或研报证据。

系统还支持真实证据源：

```text
auto：默认。本地原因库 + Futu + 巨潮 CNINFO + 规则推断。
local：本地原因库 + 规则推断。
futu：本地原因库 + Futu + 规则推断。
cninfo：本地原因库 + 巨潮 CNINFO + 规则推断。
none：只用规则推断。
```

命令行示例：

```bash
PYTHONPATH=src python3 -m ghzw.cli --date 2026-06-14 --evidence-source auto
```

Futu 主要提供研报评级、公司行动、股东变动等结构化证据；巨潮 CNINFO 主要提供公告和互动易问答。外部证据源失败不会中断日报生成，系统会自动降级到本地原因库和规则推断。

## 生成每日复盘表

```bash
PYTHONPATH=src python3 -m ghzw.cli --date 2026-06-14 --output-dir outputs/daily
```

默认会把历史 K 线缓存到：

```text
data/cache/daily_bars/
```

历史 K 线接口有频率限制，系统会自动放慢请求速度并在触发限频时等待重试。全量运行多花几十秒是正常的。

如果富途返回“历史K线额度不足”，系统会先尝试用 AkShare 补充历史 K 线并写入本地缓存；如果 AkShare 也不可用，才会降级为无 K 线。涨停、成交额、板块和资金流不受影响。

默认生成：

```text
outputs/daily/2026-06-14-daily-review.csv
outputs/daily/2026-06-14-daily-report.html
```

HTML 报告会同步总结当日涨停板块结构、板块研究候选、连板梯队、成交额核心、近期变化趋势，并在可联网且公开可访问时检索雪球及类似财经论坛。论坛内容会标注为市场讨论，不能替代公告、新闻、龙虎榜等证据。

“板块研究候选”用于把市场热度先筛出来，再决定是否深入研究。评分会综合：

```text
均涨幅
成交额
扩散度（上涨样本/活跃样本）
涨停数量
龙头/容量核心/中军信号
量比放大
短线高潮或放量滞涨风险
```

可选参数：

```bash
PYTHONPATH=src python3 -m ghzw.cli \
  --date 2026-06-14 \
  --host 127.0.0.1 \
  --port 11111 \
  --turnover-limit 30 \
  --cache-dir data/cache \
  --history-source auto \
  --output-dir outputs/daily
```

如需只生成 CSV 或跳过论坛检索：

```bash
PYTHONPATH=src python3 -m ghzw.cli --date 2026-06-14 --no-html-report
PYTHONPATH=src python3 -m ghzw.cli --date 2026-06-14 --no-forum-search
```

历史 K 线来源可选：

```text
auto：默认。配置了 TUSHARE_TOKEN 时优先 TuShare，否则用富途，最后 AkShare 兜底。
futu：优先富途，AkShare 兜底。
tushare：优先 TuShare，AkShare 兜底。
akshare：只用 AkShare。
```

## 次日验证

生成日报后，可以用 AkShare K 线做次日验证：

```bash
PYTHONPATH=src python3 -m ghzw.cli \
  --validate-report outputs/daily/2026-06-14-daily-review.csv \
  --next-date 2026-06-15 \
  --output-dir outputs/daily \
  --cache-dir data/cache \
  --history-source auto
```

默认生成：

```text
outputs/daily/2026-06-15-next-day-validation.csv
```

验证字段包括：

```text
次日开盘收益
次日最高收益
次日最大回撤
次日收盘收益
验证结论
```

## 输出字段

```text
日期
代码
名称
类型
涨停板数
收盘价
昨收
涨幅
成交额(亿元)
换手率
量比
所属行业
所属概念
核心题材
市场阶段
市场情绪
题材强度排名
题材层级
个股地位
角色分
角色依据
阶段
次日计划
资金流-净流入
资金流-主力净流入
上涨原因
原因来源
证据时间
一句话复盘
```

`成交额(亿元)` 仅用于日报展示，内部计算仍使用原始元单位；`所属行业` 会优先展示行业-细分板块，例如 `半导体-存储器/MCU芯片`。

## 本地验证

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## 目录结构

```text
src/ghzw/
  analysis.py      纯规则：涨停、题材、阶段、地位
  akshare_client.py AkShare 历史 K 线适配层
  cache.py         本地 K 线缓存
  futu_client.py   富途 OpenAPI 适配层
  history.py       缓存 + 主数据源 + 兜底数据源编排
  tushare_client.py TuShare 历史 K 线适配层
  pipeline.py      每日复盘表组装与 CSV 输出
  validation.py    次日验证
  cli.py           命令行入口
tests/
  test_analysis.py 核心规则测试
  test_pipeline.py 流水线组装测试
```
