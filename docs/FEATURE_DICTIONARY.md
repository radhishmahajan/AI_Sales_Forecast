# Feature Dictionary

Target: **NEXT_DAY_DEMAND** — units of a product sold on date D (the day after the forecast origin D-1).

All features for a row dated D use information available at the end of D-1 (or calendar facts about D).

| Feature | Family | Meaning |
|---|---|---|
| `lag_1` | lag | Units sold on the previous calendar day (D-1). 0 if the shop was closed. |
| `lag_7` | lag | Units sold 7 days earlier (same weekday last week). |
| `lag_14` | lag | Units sold 14 days earlier. |
| `lag_28` | lag | Units sold 28 days earlier. |
| `last_open_day_demand` | lag | Units sold on the most recent day the shop was open before D (handles Sunday after a closed Saturday). |
| `prev_day_open` | calendar | 1 if the shop was open on D-1, else 0. |
| `rolling_mean_7` | rolling | Mean daily units over D-7..D-1 (shift(1) then rolling 7). |
| `rolling_mean_14` | rolling | Mean daily units over D-14..D-1. |
| `rolling_mean_28` | rolling | Mean daily units over D-28..D-1. |
| `rolling_std_7` | rolling | Standard deviation of daily units over D-7..D-1 (recent volatility). |
| `rolling_max_7` | rolling | Largest daily units over D-7..D-1 (recent bulk orders). |
| `day` | calendar | Day of month of D (1-31). |
| `month` | calendar | Month of D (1-12). |
| `year` | calendar | Year of D. |
| `day_of_week` | calendar | Weekday of D (0=Monday ... 6=Sunday). |
| `week_of_year` | calendar | ISO week number of D. |
| `is_weekend` | calendar | 1 if D is Saturday or Sunday. |
| `is_month_start` | calendar | 1 if D is the first day of a month. |
| `is_month_end` | calendar | 1 if D is the last day of a month. |
| `last_known_price` | price | Most recent average selling price observed BEFORE D (held constant into the future at forecast time). |
| `avg_price_28` | price | Average daily selling price over sale days in D-28..D-1 (the 'average daily price' feature, using only past prices). |
| `price_change_pct` | price | % difference between the last known price and the 28-day average price (recent price change). |
| `sales_frequency` | history | Share of days in the product's history up to D-1 that had a sale (how regularly it sells). |
| `days_since_prev_sale` | history | Calendar days between D and the most recent sale before D. |
| `hist_mean_demand` | history | Average daily units over the product's whole history up to D-1. |
| `hist_std_demand` | history | Standard deviation of daily units over the product's history up to D-1 (demand variability). |
| `product_age_days` | history | Days since the product's first sale. |
