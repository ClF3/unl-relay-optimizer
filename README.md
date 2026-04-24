# Relay VDOT Optimizer

给定接力总时间、每名跑者的 VDOT 值，计算每个人只上场一次时的最优时间分配，使总距离最大。

项目支持三种模式：

- `concave`：把 VDOT 距离函数近似视为凹函数，求满足 KKT 条件的精确解。活跃跑者的边际距离相等。
- `search` / `time-search`：指定最小时间单位，用动态规划在离散时间格上搜索全局最优分配。
- `distance-search`：指定最小距离单位，用动态规划搜索总时间内能完成的最大距离单位数。操场起点交接时可使用 `--unit-m 400`。

## 模型

Daniels/Gilbert VDOT 经验公式：

```text
F(t) = 0.8
     + 0.1894393 e^(-0.012778t)
     + 0.2989558 e^(-0.1932605t)

VDOT = (-4.60 + 0.182258v + 0.000104v^2) / F(t)
```

其中 `t` 为分钟，`v` 为米/分钟。反解得到某个 VDOT 跑者连续跑 `t` 分钟的平均速度：

```text
v(t) =
[-0.182258 + sqrt(0.182258^2 + 4 * 0.000104 * (4.60 + VDOT * F(t)))]
/
[2 * 0.000104]
```

单人距离函数：

```text
d(t) = t * v(t)
```

优化目标：

```text
maximize   sum d_i(t_i)
subject to sum t_i = T
           t_i >= 0
```

## 快速运行

不安装包，直接用根目录入口运行：

```bash
python3 main.py --total-time 120 --vdots 62 55 48 --mode concave
```

搜索模式需要给出最小时间单位：

```bash
python3 main.py --total-time 120 --vdots 62 55 48 --mode search --unit-sec 60
```

如果交接棒只能在 400m 起点进行，用距离单位搜索：

```bash
python3 main.py --total-time 120 --vdots 62 55 48 --mode distance-search --unit-m 400
```

也可以使用逗号输入：

```bash
python3 main.py -T 90 --vdots 60,54,50,44 --mode search --unit-sec 30
```

## 参数

- `--total-time, -T`：接力总时间，单位分钟。
- `--vdots`：每名跑者的 VDOT 值，支持空格或逗号。
- `--runners, -N`：可选；用于校验人数是否等于 VDOT 个数。
- `--mode`：`concave`、`search`、`time-search` 或 `distance-search`。
- `--unit-sec`：时间搜索模式的最小时间单位，单位秒。
- `--unit-m`：距离搜索模式的最小距离单位，单位米，默认 `400`。
- `--json`：输出 JSON。
- `--quiet-warning`：隐藏凹性检查警告。

## 凹优化模式的含义

若 `d_i(t)` 为凹函数，则最优解满足：

```text
d_i'(t_i) = lambda
```

所有实际分到时间的跑者拥有相同边际收益。程序用二分搜索 `lambda`，再反解每个人的 `t_i`。

VDOT 公式下，平均速度 `v(t)` 会随时间下降，但 `d(t)` 不保证在所有时间范围全局凹。常见接力分段通常可以近似使用凹优化；若总时间很长，建议使用搜索模式验证。

## 时间搜索模式的含义

若 `--unit-sec 60`，总时间会被切成 1 分钟格。程序用动态规划枚举每个人获得多少时间格，返回离散意义下的全局最优。

复杂度约为：

```text
O(N * K^2)
```

其中 `N` 为人数，`K = 总秒数 / unit-sec`。单位越小，结果越精细，计算越慢。

## 距离搜索模式的含义

若 `--unit-m 400`，每个人分到的距离必须是 400m 的整数倍，适合“只能在操场起点交接”的规则。程序先反解：

```text
time_i(k) = 第 i 名跑者完成 k 个距离单位需要的时间
```

然后做动态规划：

```text
dp[i][u] = 前 i 名跑者完成 u 个距离单位所需的最短时间
```

最后选择 `dp[N][u] <= T` 的最大 `u`。

复杂度约为：

```text
O(N * U^2)
```

其中 `U` 是搜索到的最大距离单位数。这个模式最大化的是“完成的距离单位数”；若比赛允许最后一棒在时间结束时停在非起点位置并计入部分距离，可以把 `--unit-m` 调小获得更细的近似。

## 测试

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```
