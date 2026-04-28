# eval_report — Phase I LoRA Qwen2.5-3B-Instruct

* base    = `/data2/lrrelevant/hf_offline/hub/models--Qwen--Qwen2.5-3B-Instruct/snapshots/aa8e72537993ba99e69dfaafa59ed015b17504d1`
* adapter = `(no adapter — base-only baseline)`
* questions evaluated: **14**

## Headline metrics

| metric | value |
|---|---|
| card-id acceptable (LoRA) | **11/14** |
| card-id acceptable (rule baseline) | 13/14 |
| decision word emitted | 5/14 (eligible gold: 9)
| decision-match rate | **0/9** (0%)
| avg generation time | 24.0 s |
| avg generated length | 2093 chars |

## Per-question table

| qid | rule top-1 | gen top-1 | card-acc | gold dec | gen dec | dec-match | t (s) |
|---|---|---|---|---|---|---|---|
| q2 | card03 | card03 | ✓ | - | reject | — | 25.05 |
| q3 | card01 | card01 | ✓ | - | reject | — | 24.58 |
| q4 | card12 | card05 | ✓ | reject | - | — | 23.82 |
| q5 | card05 | card05 | ✓ | - | - | — | 24.13 |
| q6 | card09 | card09 | ✓ | reject | fail-to-reject | — | 23.91 |
| q7 | card09 | card10 | ✗ | reject | - | — | 23.99 |
| q8 | card15 | card15 | ✓ | reject | fail-to-reject | — | 24.14 |
| q9 | card16 | card16 | ✓ | reject | - | — | 23.89 |
| q10 | card19 | card18 | ✓ | fail-to-reject | - | — | 23.9 |
| q11 | card18 | card19 | ✓ | - | - | — | 23.6 |
| q12 | card20 | card20 | ✓ | reject | fail-to-reject | — | 23.74 |
| q13 | card21 | card21 | ✓ | fail-to-reject | - | — | 24.02 |
| q14 | card20 | card23 | ✗ | - | - | — | 24.0 |
| q16 | - | card15 | ✗ | reject | - | — | 23.89 |

## Generation excerpts

### ve401_local_samplefinal_q2

```
### Setup

The problem involves testing the hypothesis about the standard deviation of a population. The null hypothesis \( H_0 \) states that the standard deviation \( \sigma \) is not more than 0.00002 inch, while the alternative hypothes…
```

### ve401_local_samplefinal_q3

```
### Setup

We are given:
- Population standard deviation (\(\sigma\)) = 0.0001 inch.
- Sample size (\(n\)) = 10.
- Sample mean (\(\bar{x}\)) = 0.2546 inch.
- Hypothesized population mean (\(\mu_0\)) = 0.255 inch.
- Significance level (\(\al…
```

### ve401_local_samplefinal_q4

```
### Setup

The problem involves comparing the median pulse frequencies between two different assembly line procedures. The null hypothesis (H0) and the alternative hypothesis (H1) need to be formulated based on the given context.

### Hypot…
```

### ve401_local_samplefinal_q5

```
### Setup
We have two groups of measurements: `x` (measurements from Ball 1) and `y` (measurements from Ball 2). We will compare these groups to determine if there is a significant difference between them. The null hypothesis \(H_0\) is tha…
```

### ve401_local_samplefinal_q6

```
### Setup

We have two samples from different populations:
- Sample 1 (Formulation 1): \( n_1 = 10 \), \( \bar{x}_1 = 121 \) minutes
- Sample 2 (Formulation 2): \( n_2 = 10 \), \( \bar{x}_2 = 112 \) minutes

The population standard deviatio…
```

### ve401_local_samplefinal_q7

```
### Setup
We need to test whether the mean viscosity of the polymer using Catalyst B differs significantly from the mean viscosity using Catalyst A. We hypothesize:
- Null Hypothesis \( H_0 \): \( \mu_B = \mu_A \)
- Alternative Hypothesis \…
```

### ve401_local_samplefinal_q8

```
### Setup

We are given a sample of 98 values from the random variable \(X\), which represents the difference between the total marks (25) and the marks obtained by a student on the second midterm exam. We need to determine if this sample f…
```

### ve401_local_samplefinal_q9

```
### Setup

We are given a contingency table that represents the relationship between air quality and air temperature over 200 randomly selected days. The data is structured as follows:

| Air Quality | Poor | Fair | Good |
|-------------|--…
```

### ve401_local_samplefinal_q10

```
### Setup
We need to perform a linear regression analysis on the given data points \(x\) and \(y\), and then test the model for lack of fit at a significance level \(\alpha = 0.05\).

Given data:
\[ 
\begin{array}{c|c}
x & y \\
\hline
1.0 &…
```

### ve401_local_samplefinal_q11

```
### Setup

We have collected data on the relationship between process operating temperature (in degrees Celsius) and product yield (%). The data points are as follows:

- Temperature (T): 100, 120, 140, 160, 180
- Yield (Y): 45, 54, 66, 74,…
```

### ve401_local_samplefinal_q12

```
### Setup
We need to determine if the quadratic regression model is significant at the 5% significance level. The given data set has \( n = 7 \) points, and the coefficient of determination \( R^2 = 0.781 \).

### Hypotheses
To test the sig…
```

### ve401_local_samplefinal_q13

```
### Setup
We are given data points \((x_i, y_i)\) for \(i = 0, 1, 2, 3, 4\) as follows:
\[
\begin{array}{c|c}
x & y \\
\hline
0.50 & -0.51 \\
1.50 & -2.09 \\
2.00 & -6.03 \\
2.50 & -9.28 \\
3.50 & -17.12 \\
\end{array}
\]
The model we are f…
```

### ve401_local_samplefinal_q14

```
Let's break down the problem into the specified sections.

### Setup
We need to fit a quadratic regression model of the form \(\mu_Y = f_0 + f_1 x + f_2 x^2\) to the given data points:
\[ x: [1, 2, 4, 6, 7, 17, 29, 34, 46, 42, 52] \]
\[ y: …
```

### ve401_local_samplefinal_q16

```
To provide a structured response to your request, I will need more specific details about the problem you're referring to, such as what kind of data is being measured and what hypothesis you are testing. However, I can give you a general te…
```
