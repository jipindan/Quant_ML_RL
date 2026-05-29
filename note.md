# 量化项目学习笔记

## Horizon（预测跨度）
- Horizon 是模型预测目标的时间跨度：用当前因子值预测 N 个 bar 之后的价格涨跌
- horizon=8 表示预测 8 小时后的 log return（hourly 数据下）
- Horizon 决定 y 的构造方式：`y = log(close_{t+N} / close_t)`
- Horizon ≠ 持仓周期；可以用长 horizon 的信号做短线交易
- 不同因子族对 horizon 的敏感度不同：快信号在短 horizon 最强，慢信号在长 horizon 最强
- 快信号（动量/均线）在 h4 最强，随 horizon 增大衰减
- 慢信号（波动率/特异波动）在 h24 最强，horizon 越长信号越清晰
- 项目选择 h4 用于 Lasso_fast，h24 用于 Lasso_slow，h8 用于 meta-model

## IC / ICIR（信息系数）
- IC（Information Coefficient）= 某一截面日期内，因子值与未来 N 期收益率的 Spearman 秩相关系数
- 截面 IC：每个时间点对所有 symbol 计算一次，得到一条 IC 时间序列
- ic_mean = IC 时间序列的均值，衡量因子信号的平均强度，频率无关
- ic_std = IC 时间序列的标准差，衡量信号的稳定性
- ICIR = ic_mean / ic_std，衡量信号的风险调整后强度（类似夏普比率）
- ICIR_ann = ICIR × √(periods_per_year)，年化版本
- t_stat = ic_mean / (ic_std / √n)，对应 IC 均值是否显著不为零的 t 检验
- hit_rate = IC 符号与 ic_mean 符号相同的比例（方向一致性）
- sign_stability = 滚动 12 个月窗口中，rolling mean IC 符号与整体 IC 均值相同的比例

## 为什么从 ICIR_ann 改为 ic_mean 作为筛选标准
- ICIR_ann 含有 √(periods_per_year) 放大因子：日线 √252≈15.9，hourly √8760≈93.6
- 同等信号质量下，hourly 的 ICIR_ann 比日线高约 6 倍，0.5 的门槛在 hourly 下几乎失效
- 具体数字：日线 ICIR=0.032 → ICIR_ann=0.5（恰好过门槛）；同样的 ICIR=0.032 在 hourly 下 → ICIR_ann=3.0，轻松过
- 实测：hourly Phase 1 中 ICIR_ann 最小的存活因子达到 3.2，最强的 idio_vol_btc_168 达到 -15.1
- 真正在做筛选的是 sign_stability≥0.70：落选的 num_trades_z、dollar_vol_z 都是栽在稳定性上，不是 ICIR
- t_stat 同样因为观测量膨胀（日线 ~2000 个截面 vs hourly ~52000 个截面）被放大到 -36，失去区分度
- 这不是 bug，是 hourly 样本量大的必然结果：统计检验力极强，几乎所有因子都显著，但显著 ≠ 信号强
- ic_mean 不随观测频率变化，衡量的是每个截面上因子与收益的平均相关度，是真正频率无关的强度指标
- 新筛选标准：|ic_mean| ≥ 0.02 AND sign_stability ≥ 0.70
- sign_stability 本身也是频率无关的（比例值），保留不变

## Lookback 窗口 ≠ 持仓周期（重要区分）
- 持仓/预测周期（horizon）：你交易的频率，这个该短（hourly 交易 → horizon 几小时）
- 因子 lookback 窗口：用多少历史 bar 去计算一个信号，与持仓周期解耦
- 一个 30 天的波动率因子，不代表你要持仓 30 天
- 它是"慢变量"，告诉你当前处于高波动还是低波动 regime，这个背景信息对预测下 8 小时照样有用
- 你用长窗口算信号，但仍然做短线交易：lookback 决定信号的时间尺度，horizon 决定交易的时间尺度
- 混淆这两个概念会导致：把波动率 lookback 也卡在 1 周以内，结果用的是噪声极大的短窗口波动率估计
- 波动率的统计特性：持续性强、慢变；24h 算的波动率今天高明天低，1 周/1 月算的才是稳定 regime 信号
- 日线 Phase 1 验证：最强因子全是 60 天波动率类（idio_vol_btc_60 ICIR -3.46、rvol_60），正是因为窗口长、信号稳
- hourly Phase 1 验证：idio_vol_btc_168（1 周）是最强因子，如果卡死在 168h 以内（1 周），signal 就会弱得多

## 两组因子的区分
- 快信号（alpha 因子）：动量类、均线类、反转类
  - 代表：ret_6/12/24、dist_ma_24/72、mom_accel、bb_pos_24、rsi_24
  - 特征：衰减快，预测近期收益效果最好，horizon 越长信号越弱
  - 经济含义：市场短期动量/反转效应
- 慢信号（regime 因子）：波动率类、特异波动、流动性类
  - 代表：rvol_24/72/168、idio_vol_btc_168/336、garman_klass_24、vol_of_vol_168、amihud_illiq_24
  - 特征：慢变量，高自相关性，持续性强，预测中长期收益更稳定
  - 经济含义：当前市场所处的 regime（高波动/低波动环境）
- 快信号与慢信号的 lookback 窗口不同，但 lookback ≠ 持仓周期
- 波动率因子用长 lookback（168h=1周、336h=2周）是因为短窗口估计的波动率噪声极大

## Hourly 窗口设计原则（为什么按因子族分而非统一）
- 错误做法 A：全用短窗口（≤168h=1周）→ 动量信号合适，但波动率信号噪声极大，丢掉最强信号
- 错误做法 B：全用长窗口（720h=1月）→ 动量信号滞后严重，等同于没有日内信息
- 正确做法：按因子族分配合适的 lookback 尺度
- 动量/微观结构（快衰减）：6h、12h、24h、72h（≤3天），利用日内和短期价量信息
- 均线/反转（中速）：24h、72h（1天~3天）
- 波动率（持续性强）：24h、72h、168h（1天~1周）
- 特异波动/beta（最慢、最稳）：168h（1周）、336h（2周）
- 最长窗口 336h 而非 720h（1月）：计算量可控，同时 idio_vol_btc_336 在 hourly 下验证有效

## 窗口语义（bar 计数）
- 项目采用"bar 计数"语义：窗口数字 = bar 个数，与时间频率无关
- 日线下 window=20 表示 20 天，hourly 下 window=20 表示 20 小时
- 切换频率时窗口数字要重新设计，不能直接照搬
- hourly 窗口 profile：动量 {6,12,24,72}，均线 {24,72}，波动率 {24,72,168}，特异波动 {168,336}
- 日线窗口 profile 保持原始设计不变，两套 profile 共存于 WINDOWS dict

## 截面建模 vs 时序建模
- 截面建模：每个时间点对所有 symbol 排横截面，预测相对收益排名
  - 核心问题：symbol A 在时间 t 的因子值比 symbol B 高意味着什么？
  - IC 计算本身就是截面逻辑（Spearman 秩相关在截面上计算）
- 时序建模：对每个 symbol 独立建模，预测自己的绝对收益
- 项目采用截面排序逻辑：输出每个时间点各 symbol 的相对得分

## 两层模块化 Stacking 架构
- 第一层（base models）：
  - Lasso_fast：输入快信号因子组，目标 y=h4 return，输出 α_fast
  - Lasso_slow：输入慢信号因子组，目标 y=h24 return，输出 α_slow
  - α_fast 和 α_slow 是"融合因子"：把各组内多个原始因子压成一个分数
- 第二层（meta-model）：
  - 输入 [α_fast, α_slow]，目标 y=h8 return，输出最终信号
  - 学习快慢信号各自的贡献权重
- 三个可独立评估的信号：α_fast alone / α_slow alone / meta combined
- 模块化价值：base model 可独立升级（Lasso → XGBoost），meta 层接口不变
- meta-model 训练时必须用 out-of-sample 的 α_fast/α_slow（时序交叉验证生成），防数据泄露

## Lasso 的特点与局限
- Lasso（L1 正则化）：强制部分系数归零，实现特征稀疏化/自动特征选择
- 优点：可解释（哪些因子被选中），处理多重共线性时自动选代表
- 局限：线性模型，无法捕捉特征交叉项（x_i × x_j）
- 两组因子单独进各自 Lasso 时，因线性可加性，数学上等价于合并进一个 Lasso（同一 horizon 下）
- 但分开有价值：不同 horizon 时不等价；模块化便于后续替换

## 数据切分（防过拟合纪律）
- 时序数据不能随机 shuffle，必须按时间顺序切分
- 切分比例：train(60%) / val(20%) / test(20%)
- train：因子筛选、模型训练、超参调优
- val：模型选择、IC 验证（不参与因子筛选，防泄露）
- test：最终评估，整个项目只用一次，不可触碰

## Phase 1 Hourly Crypto 结果摘要（2026-05-30）
- 数据：17 个币种，1h interval，2020-2026，868,250 行
- 因子：29 个 hourly profile 因子（按 WINDOWS["hourly"] 展开）
- IC 筛选（horizon=8，|ic_mean|≥0.02，sign_stability≥0.70）：26/29 通过 IC，14 存活
- 最强因子：idio_vol_btc_168（ICIR_ann=-15.1，ic_mean=-0.058）、garman_klass_24（-13.5，-0.055）、rvol_72（-13.5，-0.055）
- 快信号存活：ret_6（ic_mean=-0.038）、dist_ma_24（-0.039）、dist_ma_72（-0.032）、mom_accel（-0.021）、vol_price_corr_72（-0.028）、rs_vs_btc_72（-0.023）
- 慢信号存活：idio_vol_btc_168（-0.058）、garman_klass_24（-0.055）、vol_of_vol_168（-0.040）、amihud_illiq_24（-0.035）、beta_btc_168（-0.025）
- 其他存活：vol_ratio_24（+0.013）、taker_buy_ratio_24（+0.009）、obv_slope_72（-0.009）
- 关键验证：最强信号仍是波动率/特异波动族，且都是长窗口因子（168h=1周）；印证了"波动率族单独伸到 2 周"的设计决策
- 注意：若当初把所有窗口卡在 1 周以内，idio_vol_btc_168 就变成 idio_vol_btc_24，信号会显著更弱
- Horizon 扫描发现：快信号在 h4 最强（ic_mean 绝对值最大），慢信号在 h24 最强；h8 是兼顾两组的 sweet spot

## 评估指标
- IC/ICIR：信号与未来收益的相关性（因子质量评估）
- 方向准确率：预测方向与实际方向一致的比例
- Sharpe Ratio：收益率均值 / 收益率标准差 × √年化因子，衡量风险调整后收益
- 最大回撤（Max Drawdown）：从峰值到谷值的最大跌幅
- Calmar Ratio：年化收益 / 最大回撤
- 以上指标中，IC/ICIR 用于 Phase 2 模型选择，Sharpe/回撤用于最终回测评估

## 截面 rank 变换（为什么特征和目标都要转秩）
- 问题：crypto 收益率是肥尾分布（暴涨暴跌），极端值会主导 MSE 损失
- Lasso 用 MSE 拟合，肥尾目标下少数极端样本把损失拉爆，模型为了迁就极端值会把弱信号的线性系数压到接近 0
- 后果：因子的秩相关（IC）明明很强（idio_vol@h24 = -0.081），但线性回归系数几乎为 0，整组被正则化清零
- 这是截面量化的经典坑：rank-IC 强 ≠ 线性回归（Pearson/MSE）强
- 解法：对特征和目标都做逐截面 rank 变换（每个时间戳内取百分位排名，中心化到 [-0.5, 0.5]）
- 原理：rank 把肥尾分布压成均匀分布，消除极端值；Lasso 此时拟合的是 rank→rank 关系，正好对齐 Spearman IC 的衡量方式
- rank 变换是单调的，所以因子原本的 Spearman IC 完全保留，只是去掉了量纲和outlier
- z-score（减均值除标准差）做不到这点：它是线性变换，肥尾依然是肥尾
- 实测对比：z-score 目标下 Lasso_slow 5 个系数全归零；换 rank 后立刻恢复 2/5，系数合理

## Lasso 的 L1 特征选择行为（实测观察）
- L1 正则会把弱因子/冗余因子的系数精确压到 0，等于自动特征选择
- slow 组 5 个因子里 L1 只留 2 个（idio_vol_btc_168 系数 -0.082 一骑绝尘 + garman_klass_24），其余 3 个共线因子清零
- 这从模型层面印证了"波动率本质是一个信号"：多个波动率度量高度共线，L1 只需保留信息量最大的代表
- alpha（正则强度）由 LassoCV 用 TimeSeriesSplit 在 train 内自动选；alpha 越大清零越多
- 共线因子下 L1 选哪个有随机性，但因为它们测的是同一信号，预测结果稳定（系数不稳 ≠ 预测不稳）

## 两层 Stacking 的防泄露实现
- 三段时序切分：train(60%) 训 base 模型，val(20%) 训 meta，test(20%) 只评估一次
- base 模型只在 train 拟合；base 对 val 的预测天然是 out-of-sample（base 没见过 val）
- meta 用 base 在 val 上的 OOS 预测作为输入特征训练，避免用 base 自己训练集的预测（那会泄露/过拟合）
- LassoCV 选 alpha 用 TimeSeriesSplit（按时间切，不 shuffle），整个 CV 在 train 内部完成
- rank 变换逐截面独立计算，不跨日期，所以天然不跨 train/val/test 泄露，无需分集合标准化
- 为让 base 模型的 TimeSeriesSplit 折是时间有序的，建模 DataFrame 必须先按 date 排序（panel 默认按 symbol 排）

## Phase 2 结果与结论（2026-05-30）
- 架构：Lasso_fast(快信号,h4) + Lasso_slow(慢信号,h24) → meta Ridge([α_fast,α_slow], h8)
- 因子分组（组内 corr-prune 后）：FAST 6 个、SLOW 5 个
- 测试集 IC（2024-10→2025-12，从未参与训练）：
- α_fast@h4=0.030，α_slow@h24=0.056（各自原生 horizon，慢信号更强，与 Phase 1 一致）
- 同尺度对比（都在 h8）：α_fast=0.032，α_slow=0.043，combined=0.053
- 核心结论：combined(0.053) > α_slow(0.043) > α_fast(0.032)，合并严格优于任一单组
- 这正面回答了项目的核心研究问题："在 ML 层，合并快慢两组信号确实带来 IC 增量"
- meta 权重 fast=+0.28、slow=+0.45，两组都正贡献，慢信号权重更高（与其单独更强一致）
- t_stat 全部 9~14（强显著），hit_rate ~0.55
- 这是项目的预测层 baseline；后续把 Lasso 换成树模型/LSTM，meta 层接口不变，即可进化成完整 Stacking

## 过程中遇到的工程问题与解法（debug 记录）
- 问题1：predict 在含 NaN 的全量矩阵上崩（sklearn 不接受 NaN）
- 原因：因子 warmup（序列头部）和 forward return（序列尾部）有 NaN，base 只在 valid 行训练但在全量行预测
- 解法：只在 valid 行预测，结果 scatter 进 NaN 初始化的数组（val/test 行都属于 valid，不影响）
- 问题2：Lasso 系数大面积归零（slow 0/5，fast 仅 1/6），meta 权重≈0 还把符号弄反
- 原因：z-score 目标 + 肥尾收益，MSE 被极端值主导（见上"截面 rank 变换"）
- 解法：特征和目标都改截面 rank 变换 → slow 恢复 2/5，fast 5/6，meta 权重转正且合理
- 问题3：rolling IC 图一团毛刺（hourly 迁移遗留）
- 原因：make_rolling_ic_plot 硬编码 rolling(63)，日线下=3个月但 hourly 下=2.6天，几乎不平滑
- 解法：窗口改成频率感知 ppy//4（日线 63 不变，hourly 2190=3个月），图变清晰
- 问题4：matmul overflow/divide-by-zero 警告
- 原因：α_slow 全零变成常数列，截面相关计算时 std=0 触发除零
- 解法：rank 修好 slow 后 α_slow 有方差，警告自动消失（是症状不是病因）
