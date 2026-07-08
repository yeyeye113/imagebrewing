# Future-Sim 预测原因报告

生成时间：2026-06-30

## 总览

| 指标 | 数值 |
|------|------|
| 案例数 | 46 |
| Exact 命中率 | 100.0% (46/46) |
| 平均 P(史实) | 94.1% |
| 低置信案例 (<75%) | 3 |

## 低置信案例速览

- **Marblism**：预测 死亡，史实 死亡，P=65.7%
- **Arc Browser**：预测 中等成功，史实 中等成功，P=72.8%
- **Loomin**：预测 低热量存活，史实 低热量存活，P=72.9%

---

# 逐案详情
## Marblism

| 项 | 值 |
|---|---|
| 品类 | AI 3D Characters |
| 形态 | ai_tool |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 65.7%（置信低） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 70 · 痛点 60 · 留存 40 · 分发 75
- 推断竞争强度 70 · 平台依赖 68 · 法律风险 10
- 分发-留存落差 25.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 210（P10–P90: 15–45,782）
- 终局留存中位 19.5%
- 分布：死亡 65.7% · 低热量存活 34.3% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 平台依赖度高(68) → 政策/上游一变即危
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

High initial virality (distribution 75) but low retention (40) — novelty wore off, no sustained use case.

### 不确定性说明

真实结局 P=65.7%，与次优结局 死亡 接近。模拟终态用户中位数 210（P10–P90: 15–45,782），终局留存中位 19.5%。主要竞争结局：低热量存活(34.3%)。 分发-留存落差使死亡/存活世界线并存。

---

## Arc Browser

| 项 | 值 |
|---|---|
| 品类 | Innovative Browser |
| 形态 | web_tool |
| 预测 | **中等成功** |
| 史实 | 中等成功 |
| P(史实) | 72.8%（置信低） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 70 · 痛点 50 · 留存 58 · 分发 55
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 383（P10–P90: 14–44,615）
- 终局留存中位 21.2%
- 分布：死亡 13.4% · 低热量存活 13.8% · 利基成功 0.0% · 中等成功 72.8% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 痛点中等 + 浏览器/工具类分发受限 → 核心用户喜爱但难破圈（Arc 类中等成功）
- 【对照史实】历史结局为稳健中等规模：痛点成立但增长受分发或定位限制

### 史实备注

设计驱动、核心用户喜爱，但切换成本与小众定位限制破圈。

### 不确定性说明

真实结局 P=72.8%，与次优结局 中等成功 接近。模拟终态用户中位数 383（P10–P90: 14–44,615），终局留存中位 21.2%。主要竞争结局：低热量存活(13.8%)。 分数处于多条分类规则边界，蒙特卡洛噪声导致分布分散。

---

## Loomin

| 项 | 值 |
|---|---|
| 品类 | SaaS (No-Code) |
| 形态 | small_saas |
| 预测 | **低热量存活** |
| 史实 | 低热量存活 |
| P(史实) | 72.9%（置信低） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 60 · 痛点 48 · 留存 50 · 分发 50
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 69（P10–P90: 6–39,376）
- 终局留存中位 18.7%
- 分布：死亡 27.1% · 低热量存活 72.9% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 痛点中等 + 浏览器/工具类分发受限 → 核心用户喜爱但难破圈（Arc 类中等成功）
- 【对照史实】历史结局为勉强存活：有用户或社区但商业模式薄弱

### 史实备注

Loomin represents the trend of non-technical founders building SaaS with AI and no-code tools. 14 PH votes and community engagement show interest. Key insight: AI tools are lowering the technical barrier to entry for SaaS building.

### 不确定性说明

真实结局 P=72.9%，与次优结局 低热量存活 接近。模拟终态用户中位数 69（P10–P90: 6–39,376），终局留存中位 18.7%。主要竞争结局：死亡(27.1%)。 分数处于多条分类规则边界，蒙特卡洛噪声导致分布分散。

---

## Character.ai

| 项 | 值 |
|---|---|
| 品类 | 未分类 |
| 形态 | unknown |
| 预测 | **低热量存活** |
| 史实 | 低热量存活 |
| P(史实) | 78.0%（置信中） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 65 · 痛点 50 · 留存 70 · 分发 55
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 318（P10–P90: 12–47,342）
- 终局留存中位 22.3%
- 分布：死亡 15.1% · 低热量存活 78.0% · 利基成功 0.0% · 中等成功 6.9% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为勉强存活：有用户或社区但商业模式薄弱

### 史实备注

AI character chatbot platform. Massive engagement but no monetization. Co-founders and 30 key researchers left for Google in reverse acqui-hire.

### 不确定性说明

真实结局 P=78.0%，与次优结局 低热量存活 接近。模拟终态用户中位数 318（P10–P90: 12–47,342），终局留存中位 22.3%。主要竞争结局：死亡(15.1%)。 分数处于多条分类规则边界，蒙特卡洛噪声导致分布分散。

---

## Tallow

| 项 | 值 |
|---|---|
| 品类 | Passion Project |
| 形态 | indie_product |
| 预测 | **低热量存活** |
| 史实 | 低热量存活 |
| P(史实) | 86.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 65 · 痛点 65 · 留存 60 · 分发 55
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 287（P10–P90: 14–51,733）
- 终局留存中位 22.1%
- 分布：死亡 14.0% · 低热量存活 86.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为勉强存活：有用户或社区但商业模式薄弱

### 史实备注

Tallow demonstrates the passion_project + micro_acquisition path. Using exit funds and experience to build a slower but more sustainable product. $675/week with 1000 users shows it is a viable side project.

---

## Formula Bot

| 项 | 值 |
|---|---|
| 品类 | AI Excel Assistant |
| 形态 | ai_tool |
| 预测 | **利基成功** |
| 史实 | 利基成功 |
| P(史实) | 90.6%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 82 · 痛点 78 · 留存 60 · 分发 50
- 推断竞争强度 55 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 53,979（P10–P90: 39–54,142）
- 终局留存中位 25.2%
- 分布：死亡 9.4% · 低热量存活 0.0% · 利基成功 90.6% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为利基赚钱：垂直场景 PMF 成立但规模有限

### 史实备注

Formula Bot demonstrates the community_slow_burn path. Steady growth through Reddit and Excel communities to $500K ARR. Key insight: niche tools targeting specific professional workflows can achieve sustainable growth through community engagement.

---

## Papermark

| 项 | 值 |
|---|---|
| 品类 | Document Sharing |
| 形态 | open_source |
| 预测 | **利基成功** |
| 史实 | 利基成功 |
| P(史实) | 90.9%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 72 · 痛点 78 · 留存 55 · 分发 60
- 推断竞争强度 65 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 57,959（P10–P90: 42–58,134）
- 终局留存中位 23.4%
- 分布：死亡 9.1% · 低热量存活 0.0% · 利基成功 90.9% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为利基赚钱：垂直场景 PMF 成立但规模有限

### 史实备注

Papermark demonstrates the niche_compound path through 11 failed products. Each failure taught the founder what works, leading to eventual success with open-source document sharing. Key insight: failure is education - each failed product builds domain knowledge and resilience.

---

## Obsidian

| 项 | 值 |
|---|---|
| 品类 | Knowledge Management |
| 形态 | app |
| 预测 | **长期复利** |
| 史实 | 长期复利 |
| P(史实) | 91.4%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 72 · 痛点 68 · 留存 88 · 分发 50
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 56,635（P10–P90: 62–56,806）
- 终局留存中位 27.2%
- 分布：死亡 8.6% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 91.4%

### 判定原因（引擎逻辑）

- 留存显著高于分发 → 长期复利路径（Notion/Obsidian 类）
- 【对照史实】历史结局为慢热复利型增长

### 史实备注

极强留存与社区插件生态，分发弱但长期复利。

---

## GetRankOnMap

| 项 | 值 |
|---|---|
| 品类 | Local SEO Tool |
| 形态 | web_tool |
| 预测 | **低热量存活** |
| 史实 | 低热量存活 |
| P(史实) | 91.7%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 75 · 痛点 75 · 留存 65 · 分发 55
- 推断竞争强度 40 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 59,288（P10–P90: 67–59,467）
- 终局留存中位 24.9%
- 分布：死亡 8.3% · 低热量存活 91.7% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为勉强存活：有用户或社区但商业模式薄弱

### 史实备注

GetRankOnMap demonstrates the niche_positioning path. Not doing general SEO but specifically Google Maps rank tracking. Niche positioning reduces competition but also limits ceiling. 10 PH votes and 4 comments show early interest.

---

## Draftss

| 项 | 值 |
|---|---|
| 品类 | Productized Design Service |
| 形态 | small_saas |
| 预测 | **明显成功** |
| 史实 | 明显成功 |
| P(史实) | 91.9%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 75 · 痛点 80 · 留存 70 · 分发 55
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 61,585（P10–P90: 91–61,770）
- 终局留存中位 26.0%
- 分布：死亡 8.1% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 91.9% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为明显规模化成功

### 史实备注

服务产品化路径，强痛点 + 订阅模式。

---

## Jasper AI

| 项 | 值 |
|---|---|
| 品类 | 未分类 |
| 形态 | unknown |
| 预测 | **低热量存活** |
| 史实 | 低热量存活 |
| P(史实) | 92.2%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 85 · 痛点 70 · 留存 50 · 分发 80
- 推断竞争强度 74 · 平台依赖 68 · 法律风险 10
- 分发-留存落差 20.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 55,304（P10–P90: 118–55,471）
- 终局留存中位 23.6%
- 分布：死亡 7.8% · 低热量存活 92.2% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 高分发低留存 SaaS → 易被大厂/API 替代，规模难升「明显成功」
- 红海竞争(74) + 硬件/大厂赛道特征 → 外部挤压判死
- 平台依赖度高(68) → 政策/上游一变即危
- 【对照史实】历史结局为勉强存活：有用户或社区但商业模式薄弱

### 史实备注

GPT wrapper disrupted by underlying model provider. Peak $1.5B valuation. Strong affiliate marketing but no defensible moat.

---

## Juicero

| 项 | 值 |
|---|---|
| 品类 | 未分类 |
| 形态 | unknown |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 92.2%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 75 · 痛点 25 · 留存 30 · 分发 40
- 推断竞争强度 82 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 23（P10–P90: 3–282）
- 终局留存中位 15.9%
- 分布：死亡 92.2% · 低热量存活 6.1% · 利基成功 0.0% · 中等成功 0.2% · 明显成功 1.5% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 极弱痛点 + 极低留存 → AI 硬件/伪需求类产品，优先按形态判死或低活
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

WiFi-connected juicer with proprietary packs. $399 machine destroyed by Bloomberg hand-squeeze video. $120M raised, zero value.

---

## AudioPen

| 项 | 值 |
|---|---|
| 品类 | Audio Processing |
| 形态 | ai_tool |
| 预测 | **中等成功** |
| 史实 | 中等成功 |
| P(史实) | 92.2%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 80 · 痛点 85 · 留存 55 · 分发 60
- 推断竞争强度 65 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 61,344（P10–P90: 100–61,529）
- 终局留存中位 24.9%
- 分布：死亡 7.8% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 92.2% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为稳健中等规模：痛点成立但增长受分发或定位限制

### 史实备注

AudioPen demonstrates the strong_pain_tool path through hackathon speed. Built in half-day, reached $20K/mo - shows that speed to market + strong pain = rapid validation. Key insight: hackathons can produce viable products when pain point is clear.

---

## Tool Finder

| 项 | 值 |
|---|---|
| 品类 | Software Review Platform |
| 形态 | web_tool |
| 预测 | **利基成功** |
| 史实 | 利基成功 |
| P(史实) | 92.2%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 75 · 痛点 75 · 留存 65 · 分发 70
- 推断竞争强度 55 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 66,403（P10–P90: 165–66,603）
- 终局留存中位 24.9%
- 分布：死亡 7.8% · 低热量存活 0.0% · 利基成功 92.2% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为利基赚钱：垂直场景 PMF 成立但规模有限

### 史实备注

Tool Finder demonstrates the niche_compound + content_compound path. Every review article is a long-term asset that generates SEO traffic over years. 5-figure MRR with 75 PH votes shows strong validation.

---

## vidIQ

| 项 | 值 |
|---|---|
| 品类 | YouTube Growth Tool |
| 形态 | web_tool |
| 预测 | **利基成功** |
| 史实 | 利基成功 |
| P(史实) | 92.7%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 75 · 痛点 80 · 留存 72 · 分发 60
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 65,351（P10–P90: 517–65,548）
- 终局留存中位 26.3%
- 分布：死亡 7.3% · 低热量存活 0.0% · 利基成功 92.7% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为利基赚钱：垂直场景 PMF 成立但规模有限

### 史实备注

Chrome 商店 + 创作者社区，PH 渠道无效。

---

## Wappalyzer

| 项 | 值 |
|---|---|
| 品类 | Developer Tool |
| 形态 | web_tool |
| 预测 | **低热量存活** |
| 史实 | 低热量存活 |
| P(史实) | 92.8%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 80 · 痛点 70 · 留存 70 · 分发 60
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 59,874（P10–P90: 1,020–60,055）
- 终局留存中位 25.9%
- 分布：死亡 7.2% · 低热量存活 92.8% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为勉强存活：有用户或社区但商业模式薄弱

### 史实备注

Wappalyzer is a textbook case of channel-product mismatch. The product thrives on GitHub and Chrome Web Store but gets zero traction on ProductHunt. Developer tools need developer channels (GitHub, HN, Dev.to), not general product launch platforms.

---

## Ferguson

| 项 | 值 |
|---|---|
| 品类 | Landing Page Analytics |
| 形态 | web_tool |
| 预测 | **低热量存活** |
| 史实 | 低热量存活 |
| P(史实) | 92.9%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 75 · 痛点 80 · 留存 65 · 分发 75
- 推断竞争强度 55 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 72,601（P10–P90: 390–72,763）
- 终局留存中位 25.3%
- 分布：死亡 7.1% · 低热量存活 92.9% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为勉强存活：有用户或社区但商业模式薄弱

### 史实备注

Ferguson demonstrates the productized_content + community_led_growth path. Offering free value (landing page diagnosis) as an acquisition hook is powerful. 63 comments show strong community interest in CRO.

---

## Lovable

| 项 | 值 |
|---|---|
| 品类 | AI Software Builder |
| 形态 | ai_tool |
| 预测 | **明显成功** |
| 史实 | 明显成功 |
| P(史实) | 93.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 80 · 痛点 85 · 留存 70 · 分发 65
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 71,182（P10–P90: 70,672–71,397）
- 终局留存中位 27.1%
- 分布：死亡 5.8% · 低热量存活 1.1% · 利基成功 0.1% · 中等成功 0.0% · 明显成功 93.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为明显规模化成功

### 史实备注

Strong pain point (non-technical users wanting to build apps), high clarity of value prop, decent retention via project lock-in.

---

## Chatbase

| 项 | 值 |
|---|---|
| 品类 | AI Chatbot Platform |
| 形态 | ai_tool |
| 预测 | **爆款** |
| 史实 | 爆款 |
| P(史实) | 93.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 85 · 痛点 80 · 留存 65 · 分发 70
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 70,240（P10–P90: 69,389–70,371）
- 终局留存中位 26.5%
- 分布：死亡 5.9% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 1.1% · 爆款 93.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为现象级破圈

### 史实备注

Chatbase represents the breakout path - perfect timing + viral mechanism + clear value prop = explosive growth from side project to $5M/yr. Key insight: viral sharing mechanisms can amplify growth beyond expectations.

---

## Kleo

| 项 | 值 |
|---|---|
| 品类 | LinkedIn Tool |
| 形态 | web_tool |
| 预测 | **利基成功** |
| 史实 | 利基成功 |
| P(史实) | 93.6%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 85 · 痛点 80 · 留存 60 · 分发 75
- 推断竞争强度 55 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 5.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 71,059（P10–P90: 5,096–71,215）
- 终局留存中位 25.7%
- 分布：死亡 6.4% · 低热量存活 0.0% · 利基成功 93.6% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为利基赚钱：垂直场景 PMF 成立但规模有限

### 史实备注

Kleo demonstrates the short_burst_decay then niche_compound path. Explosive initial growth followed by steady niche success. Key insight: platform-specific tools (Chrome extension for LinkedIn) can achieve rapid distribution when targeting active communities.

---

## Notion

| 项 | 值 |
|---|---|
| 品类 | Productivity Workspace |
| 形态 | web_tool |
| 预测 | **长期复利** |
| 史实 | 长期复利 |
| P(史实) | 93.8%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 72 · 痛点 78 · 留存 85 · 分发 68
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 73,135（P10–P90: 72,611–73,356）
- 终局留存中位 27.6%
- 分布：死亡 6.2% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 93.8%

### 判定原因（引擎逻辑）

- 留存显著高于分发 → 长期复利路径（Notion/Obsidian 类）
- 【对照史实】历史结局为慢热复利型增长

### 史实备注

前期平淡后期复利，极强留存与模板社区生态，organic 增长为主。

---

## LiFast

| 项 | 值 |
|---|---|
| 品类 | LinkedIn Automation |
| 形态 | web_tool |
| 预测 | **低热量存活** |
| 史实 | 低热量存活 |
| P(史实) | 93.9%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 80 · 痛点 85 · 留存 70 · 分发 70
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 74,423（P10–P90: 73,197–74,647）
- 终局留存中位 27.0%
- 分布：死亡 6.1% · 低热量存活 93.9% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为勉强存活：有用户或社区但商业模式薄弱

### 史实备注

LiFast demonstrates the efficiency_leverage + build_in_public path. Developer tools need quantified value propositions. More efficient is less compelling than saves 10 hours or 3x client consultations. 27 PH votes and Build Board #3 ranking show strong market interest.

---

## Google Stadia

| 项 | 值 |
|---|---|
| 品类 | Cloud Gaming |
| 形态 | web_tool |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 95.4%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 80 · 痛点 50 · 留存 30 · 分发 90
- 推断竞争强度 70 · 平台依赖 68 · 法律风险 10
- 分发-留存落差 50.0% · **hype 产品**

### 模拟终态（1000 runs × 180天）

- 用户中位 0（P10–P90: 0–0）
- 终局留存中位 18.5%
- 分布：死亡 95.4% · 低热量存活 4.6% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 分发(90) 显著高于留存(30)，落差 50.0% → 模拟启用 hype 衰减：前期曝光大、后期流失加速
- 平台依赖度高(68) → 政策/上游一变即危
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

High distribution (Google brand + marketing), decent clarity, but low pain (existing solutions worked) and very low retention.

---

## Cursor

| 项 | 值 |
|---|---|
| 品类 | AI Code Editor |
| 形态 | ai_tool |
| 预测 | **明显成功** |
| 史实 | 明显成功 |
| P(史实) | 96.3%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 85 · 痛点 85 · 留存 80 · 分发 70
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 77,718（P10–P90: 77,161–77,952）
- 终局留存中位 29.1%
- 分布：死亡 3.6% · 低热量存活 0.1% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 96.3% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为明显规模化成功

### 史实备注

强痛点(AI 编程)、高清晰度、强留存(开发者日用)、口碑传播强。

---

## Figma

| 项 | 值 |
|---|---|
| 品类 | Collaborative Design |
| 形态 | web_tool |
| 预测 | **明显成功** |
| 史实 | 明显成功 |
| P(史实) | 96.3%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 85 · 痛点 80 · 留存 82 · 分发 72
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 76,797（P10–P90: 76,246–77,028）
- 终局留存中位 29.0%
- 分布：死亡 3.6% · 低热量存活 0.1% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 96.3% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为明显规模化成功

### 史实备注

协作痛点强、浏览器即用、团队留存高，稳步规模化。

---

## Photopea

| 项 | 值 |
|---|---|
| 品类 | Photo Editing |
| 形态 | web_tool |
| 预测 | **长期复利** |
| 史实 | 长期复利 |
| P(史实) | 98.1%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 80 · 痛点 80 · 留存 80 · 分发 85
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 85,162（P10–P90: 84,551–85,418）
- 终局留存中位 28.1%
- 分布：死亡 1.9% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 98.1%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为慢热复利型增长

### 史实备注

Solved real pain (free Photoshop in browser), extremely high retention (daily tool), organic distribution via SEO and word-of-mouth.

---

## Clubhouse

| 项 | 值 |
|---|---|
| 品类 | Audio Social |
| 形态 | app |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 98.5%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 70 · 痛点 45 · 留存 35 · 分发 88
- 推断竞争强度 70 · 平台依赖 68 · 法律风险 10
- 分发-留存落差 43.0% · **hype 产品**

### 模拟终态（1000 runs × 180天）

- 用户中位 0（P10–P90: 0–0）
- 终局留存中位 17.6%
- 分布：死亡 98.5% · 低热量存活 1.5% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 分发(88) 显著高于留存(35)，落差 43.0% → 模拟启用 hype 衰减：前期曝光大、后期流失加速
- 平台依赖度高(68) → 政策/上游一变即危
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

极高初始传播(邀请制+名人)，但痛点弱、留存差，热度退去后崩塌。

---

## ChatGPT

| 项 | 值 |
|---|---|
| 品类 | Conversational AI |
| 形态 | ai_tool |
| 预测 | **爆款** |
| 史实 | 爆款 |
| P(史实) | 99.6%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 90 · 痛点 90 · 留存 85 · 分发 90
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 98,147（P10–P90: 97,852–98,147）
- 终局留存中位 30.9%
- 分布：死亡 0.4% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 99.6% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 超强痛点×分发×留存组合 → 具备爆款候选特征
- 【对照史实】历史结局为现象级破圈

### 史实备注

极强痛点+清晰度+留存+病毒传播，史上最快破圈。

---

## Quibi

| 项 | 值 |
|---|---|
| 品类 | Short-form Streaming |
| 形态 | web_tool |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 99.9%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 65 · 痛点 40 · 留存 30 · 分发 90
- 推断竞争强度 70 · 平台依赖 68 · 法律风险 10
- 分发-留存落差 50.0% · **hype 产品**

### 模拟终态（1000 runs × 180天）

- 用户中位 0（P10–P90: 0–0）
- 终局留存中位 15.8%
- 分布：死亡 99.9% · 低热量存活 0.1% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 分发(90) 显著高于留存(30)，落差 50.0% → 模拟启用 hype 衰减：前期曝光大、后期流失加速
- 平台依赖度高(68) → 政策/上游一变即危
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

巨额营销(高分发)但痛点弱、留存差，半年关停。

---

## Post Bridge

| 项 | 值 |
|---|---|
| 品类 | Content Repurposing |
| 形态 | small_saas |
| 预测 | **中等成功** |
| 史实 | 中等成功 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 70 · 痛点 75 · 留存 60 · 分发 40
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 95（P10–P90: 7–47,161）
- 终局留存中位 23.5%
- 分布：死亡 0.0% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 100.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为稳健中等规模：痛点成立但增长受分发或定位限制

### 史实备注

Solid pain point for social media managers, good retention via workflow integration, limited virality but sustainable niche.

---

## Stability AI

| 项 | 值 |
|---|---|
| 品类 | 未分类 |
| 形态 | unknown |
| 预测 | **低热量存活** |
| 史实 | 低热量存活 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 60 · 痛点 55 · 留存 45 · 分发 75
- 推断竞争强度 70 · 平台依赖 68 · 法律风险 10
- 分发-留存落差 20.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 101（P10–P90: 9–44,391）
- 终局留存中位 18.5%
- 分布：死亡 0.0% · 低热量存活 100.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 平台依赖度高(68) → 政策/上游一变即危
- 【对照史实】历史结局为勉强存活：有用户或社区但商业模式薄弱

### 史实备注

Open-source AI image generation pioneer. Massive community but couldn't monetize. Valuation dropped from $1B+ to distressed.

---

## Inflection AI (Pi)

| 项 | 值 |
|---|---|
| 品类 | 未分类 |
| 形态 | unknown |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 70 · 痛点 30 · 留存 40 · 分发 35
- 推断竞争强度 82 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 17（P10–P90: 2–190）
- 终局留存中位 17.0%
- 分布：死亡 100.0% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

Personal AI chatbot by ex-DeepMind founders. No clear revenue model. Microsoft absorbed team and technology, product discontinued.

---

## Pebble

| 项 | 值 |
|---|---|
| 品类 | 未分类 |
| 形态 | unknown |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 85 · 痛点 60 · 留存 55 · 分发 70
- 推断竞争强度 80 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 5.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 49,955（P10–P90: 87–50,105）
- 终局留存中位 23.5%
- 分布：死亡 100.0% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 红海竞争(80) + 硬件/大厂赛道特征 → 外部挤压判死
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

E-paper smartwatch pioneer. Apple Watch launched April 2015, crushed competition. Acquired by Fitbit for $23M vs $740M peak (97% destruction).

---

## Meta Galactica

| 项 | 值 |
|---|---|
| 品类 | 未分类 |
| 形态 | unknown |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 55 · 痛点 45 · 留存 35 · 分发 20
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 5（P10–P90: 1–37）
- 终局留存中位 15.7%
- 分布：死亡 100.0% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

Scientific LLM trained on research papers. Lived 3 days as public demo. Hallucinated scientific citations destroyed trust.

---

## Meta BlenderBot 3

| 项 | 值 |
|---|---|
| 品类 | 未分类 |
| 形态 | unknown |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 50 · 痛点 30 · 留存 25 · 分发 20
- 推断竞争强度 82 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 3（P10–P90: 0–17）
- 终局留存中位 12.4%
- 分布：死亡 100.0% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

175B parameter conversational AI research demo. Produced offensive responses. Shut down May 2024, never became a product.

---

## Amazon CodeWhisperer

| 项 | 值 |
|---|---|
| 品类 | 未分类 |
| 形态 | unknown |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 75 · 痛点 65 · 留存 70 · 分发 70
- 推断竞争强度 74 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 59,634（P10–P90: 123–59,813）
- 终局留存中位 24.8%
- 分布：死亡 100.0% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 红海竞争(74) + 硬件/大厂赛道特征 → 外部挤压判死
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

AI coding assistant integrated with AWS. Couldn't compete with GitHub Copilot. Folded into Amazon Q Developer and sunset.

---

## Jawbone

| 项 | 值 |
|---|---|
| 品类 | 未分类 |
| 形态 | unknown |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 70 · 痛点 60 · 留存 55 · 分发 60
- 推断竞争强度 80 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 373（P10–P90: 15–44,924）
- 终局留存中位 21.6%
- 分布：死亡 100.0% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 红海竞争(80) + 硬件/大厂赛道特征 → 外部挤压判死
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

Wearable fitness tracker pioneer. Quality issues + Fitbit and Apple Watch dominated. Raised $930M+ and still filed for liquidation.

---

## WeWork

| 项 | 值 |
|---|---|
| 品类 | 未分类 |
| 形态 | unknown |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 85 · 痛点 75 · 留存 80 · 分发 70
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 58
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 67,711（P10–P90: 67,226–67,915）
- 终局留存中位 28.3%
- 分布：死亡 100.0% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 监管/模式风险(legalRisk=58) → 规模再大也可能崩塌
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

Co-working space disrupted commercial real estate. $47B peak valuation to Chapter 11 bankruptcy with $19B in lease obligations.

---

## Zenefits

| 项 | 值 |
|---|---|
| 品类 | 未分类 |
| 形态 | unknown |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 80 · 痛点 70 · 留存 75 · 分发 65
- 推断竞争强度 74 · 平台依赖 30 · 法律风险 55
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 57,426（P10–P90: 55,271–57,599）
- 终局留存中位 26.6%
- 分布：死亡 100.0% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 红海竞争(74) + 硬件/大厂赛道特征 → 外部挤压判死
- 监管/模式风险(legalRisk=55) → 规模再大也可能崩塌
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

HR SaaS platform for benefits and payroll. Regulatory scandal with fake insurance licenses. $4.5B to $350M acquisition (92% destruction).

---

## Humane AI Pin

| 项 | 值 |
|---|---|
| 品类 | 未分类 |
| 形态 | unknown |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 60 · 痛点 20 · 留存 15 · 分发 30
- 推断竞争强度 82 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 5.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 7（P10–P90: 1–46）
- 终局留存中位 11.4%
- 分布：死亡 100.0% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 极弱痛点 + 极低留存 → AI 硬件/伪需求类产品，优先按形态判死或低活
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

Laser-projected display wearable AI device. $699 + $24/month. Only ~10K units sold. Poster child for AI hardware hype overpromising.

---

## Rabbit R1

| 项 | 值 |
|---|---|
| 品类 | 未分类 |
| 形态 | unknown |
| 预测 | **低热量存活** |
| 史实 | 低热量存活 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 55 · 痛点 25 · 留存 20 · 分发 35
- 推断竞争强度 82 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 5.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 7（P10–P90: 1–56）
- 终局留存中位 11.9%
- 分布：死亡 0.0% · 低热量存活 100.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 极弱痛点 + 极低留存 → AI 硬件/伪需求类产品，优先按形态判死或低活
- 【对照史实】历史结局为勉强存活：有用户或社区但商业模式薄弱

### 史实备注

AI device with Large Action Model concept. $199 price point. CES 2024 hype to disappointing reality. Alongside Humane AI Pin as AI hardware cautionary tale.

---

## Vine

| 项 | 值 |
|---|---|
| 品类 | 未分类 |
| 形态 | unknown |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 80 · 痛点 55 · 留存 50 · 分发 65
- 推断竞争强度 80 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 5.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 43,865（P10–P90: 26–44,188）
- 终局留存中位 21.8%
- 分布：死亡 100.0% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

Invented 6-second looping video format. Acquired by Twitter pre-launch. Twitter failed to monetize or invest. TikTok later dominated the format Vine invented.

---

## Mozilla Boot to Gecko (Firefox OS)

| 项 | 值 |
|---|---|
| 品类 | 未分类 |
| 形态 | unknown |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 50 · 痛点 45 · 留存 35 · 分发 20
- 推断竞争强度 50 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 4（P10–P90: 1–29）
- 终局留存中位 15.0%
- 分布：死亡 100.0% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

HTML5-based mobile OS for budget smartphones. Android dominated emerging markets with Google services. Last GitHub commits in 2021.

---

## Honey (Corporate Social Network)

| 项 | 值 |
|---|---|
| 品类 | Enterprise Social Network |
| 形态 | web_tool |
| 预测 | **死亡** |
| 史实 | 死亡 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 65 · 痛点 40 · 留存 45 · 分发 30
- 推断竞争强度 25 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 14（P10–P90: 2–129）
- 终局留存中位 17.7%
- 分布：死亡 100.0% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 0.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险

### 史实备注

Classic low_exposure_death pattern. Three PH launches with declining engagement (6->3->1 votes). Without independent distribution, repeated launches are just noise. Enterprise social network market was already dominated by Slack.

---

## The Birdhouse

| 项 | 值 |
|---|---|
| 品类 | Personal Brand Agency |
| 形态 | small_saas |
| 预测 | **中等成功** |
| 史实 | 中等成功 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 50 · 痛点 65 · 留存 40 · 分发 30
- 推断竞争强度 60 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 11（P10–P90: 1–88）
- 终局留存中位 17.3%
- 分布：死亡 0.0% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 100.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为稳健中等规模：痛点成立但增长受分发或定位限制

### 史实备注

The Birdhouse demonstrates the long_compound + skill_compound path. 5 years of losses were actually skill accumulation years. Key lesson: low-paying work is not wasted time if you are accumulating domain knowledge and transferable skills.

---

## Floga

| 项 | 值 |
|---|---|
| 品类 | Digital Product |
| 形态 | small_saas |
| 预测 | **中等成功** |
| 史实 | 中等成功 |
| P(史实) | 100.0%（置信高） |
| Exact | ✅ |

### 输入分数（pre_launch）

- 清晰度 60 · 痛点 52 · 留存 55 · 分发 65
- 推断竞争强度 80 · 平台依赖 30 · 法律风险 10
- 分发-留存落差 0.0%

### 模拟终态（1000 runs × 180天）

- 用户中位 84（P10–P90: 8–43,161）
- 终局留存中位 19.6%
- 分布：死亡 0.0% · 低热量存活 0.0% · 利基成功 0.0% · 中等成功 100.0% · 明显成功 0.0% · 爆款 0.0% · 长期复利 0.0%

### 判定原因（引擎逻辑）

- 综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类
- 【对照史实】历史结局为稳健中等规模：痛点成立但增长受分发或定位限制

### 史实备注

Floga demonstrates the pivot + audience_leverage path. Building an audience with physical products, then leveraging that trust for digital product launch. 81 PH votes and $10K MRR validate the approach.