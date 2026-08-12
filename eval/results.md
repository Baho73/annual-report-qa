# Результаты замера

## Сводка по режимам

| Режим | Пройдено | Числа верны | Страницы верны | Медиана токенов | Медиана задержки | Цена набора |
|---|---|---|---|---|---|---|
| `router` | 10/10 | 7/7 | 8/8 | 36 416 | 17.25 с | $8.07 |
| `full` | 5/10 | 3/3 | 4/4 | 206 245 | 15.03 с | $10.70 |

## По вопросам

| Вопрос | Тип | Режим | Итог | Числа | Страницы | Токены | Задержка | Цена |
|---|---|---|---|---|---|---|---|---|
| Q1-revenue | fact | `router` | пройден | да | да | 33390 | 18.82 с | $0.312 |
| Q2-growth | aggregate | `router` | пройден | да | да | 114562 | 22.71 с | $1.151 |
| Q3-risks | narrative | `router` | пройден | — | да | 13525 | 17.25 с | $0.145 |
| Q4-profit | causal | `router` | пройден | да | да | 113410 | 27.22 с | $1.153 |
| Q5-invest | boundary | `router` | пройден | — | — | 211282 | 51.9 с | $2.179 |
| Q6-segment | fact | `router` | пройден | да | да | 14200 | 8.7 с | $0.112 |
| Q7-ebitda | fact | `router` | пройден | да | да | 36416 | 12.73 с | $0.338 |
| Q8-netprofit | fact | `router` | пройден | да | да | 33444 | 15.64 с | $0.294 |
| Q9-absent | refusal | `router` | пройден | — | — | 211936 | 17.1 с | $2.075 |
| Q10-intersegment | causal | `router` | пройден | да | да | 32242 | 16.39 с | $0.308 |
| Q1-revenue | fact | `full` | пройден | да | да | 206245 | 15.03 с | $2.094 |
| Q2-growth | aggregate | `full` | пройден | да | да | 206265 | 23.56 с | $2.132 |
| Q3-risks | narrative | `full` | пройден | — | да | 206249 | 38.69 с | $2.142 |
| Q4-profit | causal | `full` | пройден | да | да | 206250 | 27.34 с | $2.144 |
| Q5-invest | boundary | `full` | пройден | — | — | 206247 | 38.58 с | $2.183 |
| Q6-segment | fact | `full` | провал | — | — | 0 | 0.0 с | $0.000 |
| Q7-ebitda | fact | `full` | провал | — | — | 0 | 0.0 с | $0.000 |
| Q8-netprofit | fact | `full` | провал | — | — | 0 | 0.0 с | $0.000 |
| Q9-absent | refusal | `full` | провал | — | — | 0 | 0.0 с | $0.000 |
| Q10-intersegment | causal | `full` | провал | — | — | 0 | 0.0 с | $0.000 |

## Числа без подтверждения в контексте

- Q4-profit (`router`): 39.6, 56.2, 6.5, 8.7
- Q5-invest (`router`): 20254582.5, 39.6
- Q6-segment (`router`): 31.1, 34.1
- Q7-ebitda (`router`): 15.4
- Q10-intersegment (`router`): 31.1, 34.1, 8.3
- Q4-profit (`full`): 39.6, 56.2, 6.5, 8.7
- Q5-invest (`full`): 1.799, 39.6

## Ошибки прогона

- Q6-segment (`full`): OpenRouter вернул 403: {"error":{"message":"Key limit exceeded (daily limit). Manage it using https://openrouter.ai/workspaces/default/keys/d615a0b64896c0d8bd8c0ba32b5813152f29eb5b0a4f79ba7f3f37679f3cca35","code":403}}
- Q7-ebitda (`full`): OpenRouter вернул 403: {"error":{"message":"Key limit exceeded (daily limit). Manage it using https://openrouter.ai/workspaces/default/keys/d615a0b64896c0d8bd8c0ba32b5813152f29eb5b0a4f79ba7f3f37679f3cca35","code":403}}
- Q8-netprofit (`full`): OpenRouter вернул 403: {"error":{"message":"Key limit exceeded (daily limit). Manage it using https://openrouter.ai/workspaces/default/keys/d615a0b64896c0d8bd8c0ba32b5813152f29eb5b0a4f79ba7f3f37679f3cca35","code":403}}
- Q9-absent (`full`): OpenRouter вернул 403: {"error":{"message":"Key limit exceeded (daily limit). Manage it using https://openrouter.ai/workspaces/default/keys/d615a0b64896c0d8bd8c0ba32b5813152f29eb5b0a4f79ba7f3f37679f3cca35","code":403}}
- Q10-intersegment (`full`): OpenRouter вернул 403: {"error":{"message":"Key limit exceeded (daily limit). Manage it using https://openrouter.ai/workspaces/default/keys/d615a0b64896c0d8bd8c0ba32b5813152f29eb5b0a4f79ba7f3f37679f3cca35","code":403}}
