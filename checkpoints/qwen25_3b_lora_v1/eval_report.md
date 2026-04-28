# eval_report — Phase I LoRA Qwen2.5-3B-Instruct

* base    = `/data2/lrrelevant/hf_offline/hub/models--Qwen--Qwen2.5-3B-Instruct/snapshots/aa8e72537993ba99e69dfaafa59ed015b17504d1`
* adapter = `/data2/lrrelevant/ve401-solver/checkpoints/qwen25_3b_lora_v1`
* questions evaluated: **14**

## Headline metrics

| metric | value |
|---|---|
| card-id acceptable (LoRA) | **5/14** |
| card-id acceptable (rule baseline) | 13/14 |
| decision word emitted | 5/14 (eligible gold: 9)
| decision-match rate | **1/9** (11%)
| avg generation time | 37.6 s |
| avg generated length | 929 chars |

## Per-question table

| qid | rule top-1 | gen top-1 | card-acc | gold dec | gen dec | dec-match | t (s) |
|---|---|---|---|---|---|---|---|
| q2 | card03 | card03 | ✓ | - | fail-to-reject | — | 29.06 |
| q3 | card01 | card02 | ✗ | - | - | — | 50.2 |
| q4 | card12 | card05 | ✓ | reject | fail-to-reject | — | 13.27 |
| q5 | card05 | card10 | ✓ | - | - | — | 49.49 |
| q6 | card09 | card15 | ✗ | reject | - | — | 49.49 |
| q7 | card09 | - | ✗ | reject | - | — | 49.47 |
| q8 | card15 | - | ✗ | reject | - | — | 49.51 |
| q9 | card16 | card02 | ✗ | reject | - | — | 49.07 |
| q10 | card19 | card19 | ✓ | fail-to-reject | reject | — | 23.53 |
| q11 | card18 | - | ✗ | - | - | — | 48.99 |
| q12 | card20 | card20 | ✓ | reject | fail-to-reject | — | 12.79 |
| q13 | card21 | card19 | ✗ | fail-to-reject | fail-to-reject | ✓ | 48.85 |
| q14 | card20 | - | ✗ | - | - | — | 49.3 |
| q16 | - | - | ✗ | reject | - | — | 3.63 |

## Generation excerpts

### ve401_local_samplefinal_q2

```
## Solution
We will perform a hypothesis test on σ : H0 : σ ≤ 0:00002; H1 : σ > 0:00002. The statistic follows a chi-square distribution with n = 7 degrees of freedom. Since we are testing for a larger variance, we need to flip the rejectio…
```

### ve401_local_samplefinal_q3

```
## Solution
We test H0 : μ = 0:255 H1 : μ 6= 0:255 The statistic is Z = p σ√ n X - μ0 = p 0:0001 10 0:2546 - 0:255 ∼ N (0; 1): 0:0001 10 0:2546 - 0:255 0:0001 10 0:0001 10 0:2546 - 0:255 0:0001 10 0:2546 - 0:255 0:0001 10 0:2546 - 0:255 0:0…
```

### ve401_local_samplefinal_q4

```
## Solution
H0 : The median pulse frequency is the same for both procedures. H1 : The median pulse frequency is higher for Procedure 2 than for Procedure 1. (2 Marks) The Wilcoxon signed rank test gives a test statistic of W = 105.5. Since …
```

### ve401_local_samplefinal_q5

```
## Solution
We have n = 10 pairs of measurements. We calculate the differences D i = x i - y i : D i Syy i 1 23 100 2 -15 225 3 14 196 4 -4 16 5 16 256 6 -10 100 7 9 81 8 -2 4 9 17 289 10 5 25 Total 85 1495 We then calculate the statistic f…
```

### ve401_local_samplefinal_q6

```
## Solution
We test H0 : µ1 - µ2 ≤ 10 H1 : µ1 - µ2 > 10 The statistic follows a normal distribution N (1, 2σ2 ) with σ2 = 64. So we have Z = √ 2 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10…
```

### ve401_local_samplefinal_q7

```
*Slide refs:* slide 544, slide 545, slide 546, slide 547, slide 548, slide 549, slide 550, slide 551, slide 552, slide 553, slide 554, slide 555, slide 556, slide 557, slide 558, slide 559, slide 560, slide 561, slide 562, slide 563, slide …
```

### ve401_local_samplefinal_q8

```
*Slide refs:* slide 494

## Solution
The stem-and-leaf diagram is shown below. There are 25 stems, corresponding to the 25 possible values of X. 25 24 23 22 21 20 19 18 17 16 15 14 13 12 11 10 9 8 7 6 5 4 3 2 1 0 1 2 3 4 5 6 7 8 9 10 11 12 …
```

### ve401_local_samplefinal_q9

```
## Solution
We will use the statistic , where is the pooled sample standard deviation. We have , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , , ,…
```

### ve401_local_samplefinal_q10

```
## Solution
We first calculate the necessary sums: ∑x = 21.0, ∑y = 40.5, ∑x2 = 65.3, ∑y2 = 204.5, ∑xy = 76.5. (1/2 Mark) We then calculate the means: x = 21=5, y = 40:5=10 = 4:05. (1/2 Mark) The values of b1; b0 are calculated as follows: b…
```

### ve401_local_samplefinal_q11

```
## Solution
We have n = 5 observations. We ﬁnd b1 = 10∑ i=1 (xi - x)(yi - y) 10∑ i=1 (xi - x)2 = 10∑ i=1 xi yi - n x y 10∑ i=1 x2 i - n x2 = 10∑ i=1 xi yi - 5 x y 10∑ i=1 x2 i - 5 x2 = 10∑ i=1 xi yi - 5 x y 10∑ i=1 x2 i - 5 x2 = 10∑ i=1 xi …
```

### ve401_local_samplefinal_q12

```
## Solution
You have applied a quadratic regression model to a data set of n = 7 points. Your computer algebra system tells you that R2 = 0:781. Is the regression significant at the α = 5% level? (3 Marks) Solution We test H0 : regression i…
```

### ve401_local_samplefinal_q13

```
*Slide refs:* slide 702

## Solution
We have n = 5, so we need to calculate bμ = b0 + b1x + b2x2 : We have X T X = 1 0:5 2:25 1 1:5 6:25 1 2:5 15:625 and X T Y = -1:5 1:5 -1:5 2:5 -6:5 so b = (X T X)-1X T Y = 0 @ 0:1167 -0:2929 0:0512 -0:29…
```

### ve401_local_samplefinal_q14

```
## Solution
We have X T X = 1 7 0 -9 17 -9 17 -9 67=12 -2=3 1 -2=3 1=12 1 -2=3 1=12 1: (1 Mark) The hat matrix is H = X(X T X)-1X T = 1 7 0 -9 17 -9 17 -9 67=12 -2=3 1 -2=3 1=12 1 -2=3 1=12 1: (1 Mark) The leverage values are hii = 1 7 0 -9…
```

### ve401_local_samplefinal_q16

```
## Diagnostic+Remedy
Sign: \(s^2\) used as \(\sigma^2\); Move: use \(S^2=\sum(X_i-\bar X)^2/(n-1)\), not \((X_i-\bar X)^2\).
```
