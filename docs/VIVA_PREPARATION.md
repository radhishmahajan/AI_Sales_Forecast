# Viva and Presentation Preparation

> Numbers below come from the latest real training run (2026-11-14T17:26:46Z). Regenerate with `python scripts/generate_docs.py`.

## Abstract in simple language
A shop needs to know how much of each product to buy. We took one year of real sales from a UK online gift wholesaler
(541,909 invoice lines). First we cleaned the data: we separated real sales from returns, cancelled orders,
postage and duplicates. Then we taught computer models to predict tomorrow's sales of each product from recent sales, the weekday
and price, and checked honestly whether they beat simple rules like "same as the last 7 days". Finally, the predictions plus the
shop's current stock and supplier delivery time tell the user when to reorder and how much. Everything runs in a web dashboard,
without a database.

## Two-minute introduction
"Good morning. Our project is an AI-based sales forecasting and inventory optimisation system. Retailers often reorder by guesswork,
which causes either stockouts or excess stock. We used the real UCI Online Retail dataset, about 540 thousand transactions from
2010–2011. Our pipeline validates the Excel file, labels every row (sale, return, cancelled order, postage, adjustment), and builds
a daily demand table for the 500 best-documented products. We engineered lag, rolling-average, calendar,
price and history features while carefully avoiding data leakage, and compared three simple baselines with Linear Regression, Random
Forest, HistGradientBoosting and XGBoost using time-based validation. The selected model, HistGradientBoosting, achieves a test error of about
21.3 units per day. We report honestly that it only matches the 7-day-average
baseline on the final test period. The model produces 7-, 14- and 30-day forecasts. Combined with stock and lead time entered by
the user, these give safety stock, reorder point and order quantity. Everything is available through a FastAPI backend and a React
dashboard, and all data is stored in files instead of a database."

## Five-minute explanation (talking points)
1. **Problem and data (45 s):** why forecasting matters; UCI dataset; what it lacks (no stock data → user inputs).
2. **Data understanding and cleaning (60 s):** 541,909 rows → 519,735 clean sales; duplicates;
   cancellations matched to orders; outliers kept unless they were reversed; target = gross fulfilled demand.
3. **EDA (45 s):** UK 84.7% of revenue; November peak; no Saturday trading; most products erratic.
4. **Features and leakage (60 s):** product-day panel; shift-before-rolling; date split; rolling-origin CV.
5. **Models and results (60 s):** baselines vs 4 models; Poisson loss; selected HistGradientBoosting; test MAE 21.27,
   WAPE 89.2%; honest baseline comparison; feature importance.
6. **Forecast and inventory (45 s):** recursive forecasts; SS / ROP / target formulas; statuses and alerts; what-if simulator.
7. **System (25 s):** FastAPI + React, 8 pages, file storage, tests, reports.

## Problem statement
Forecast daily product demand from historical transactions without future information, and convert forecasts plus user-entered
stock and lead times into explainable reorder recommendations, locally and without a database.

## Objectives
See PROJECT_REPORT.md §6.

## Methodology in one diagram
Excel → validate → label & clean → EDA → daily panel → features (shift 1) → date split → baselines + models (rolling-origin tuning)
→ select on validation → test once → recursive forecast → inventory policy → API → dashboard.

## Every ML algorithm in simple words
* **Linear Regression:** draws the best straight-line relationship between the features and demand.
* **Random Forest:** asks hundreds of slightly different decision trees and averages their answers.
* **HistGradientBoosting:** builds trees one by one; each new tree fixes the mistakes of the previous ones. Fast because it groups
  values into bins.
* **XGBoost:** a highly optimised, regularised version of gradient boosting.
* **Baselines:** "same as yesterday", "same as last week", "average of the last 7 days".

## Preprocessing in simple words
Remove exact copies → give every row a label → keep only real sales as demand → match cancellations to the orders they cancel →
clean product names → flag (but keep) unusually big orders.

## Feature engineering in simple words
For each product and day we describe what we knew yesterday: sales yesterday, a week ago, 2 and 4 weeks ago, recent averages,
the biggest recent order, how often it sells, the last price, and today's weekday and month. Nothing from "today" or later is used.

## Forecasting in simple words
The model predicts tomorrow. We pretend that prediction happened, slide forward one day, and repeat for 7, 14 or 30 days.

## Inventory formulas in simple words
* Safety stock: a cushion for unpredictable days = Z × daily variability × √(lead time).
* Reorder point: expected sales while waiting for delivery plus the cushion.
* Target stock: enough to last until the delivery arrives and until the next review, plus the cushion.
* Order quantity: target minus what you have, rounded to the supplier's minimum order and pack size, and capped by storage.

## Technology-stack justification
| Choice | Why |
|---|---|
| pandas / NumPy | Standard, fast tabular processing |
| scikit-learn | Pipelines, models, RandomizedSearchCV, permutation importance in one consistent API |
| XGBoost | Strong gradient boosting with Poisson/Tweedie objectives |
| Parquet / JSON / CSV / Joblib | Database-free storage: Parquet is fast and typed, JSON is readable, CSV opens in Excel, Joblib stores fitted models |
| FastAPI + Pydantic | Automatic validation, Swagger docs, fast, type-hinted |
| React + TypeScript + Vite | Component-based UI; type safety catches errors early; fast builds |
| Tailwind CSS | Consistent, modern styling without large CSS files |
| Recharts | Declarative React charts fed directly from the API |
| pytest / Vitest | Automated backend and frontend tests |

## 50 important viva questions with answers
**Q1. What is the goal of your project?**  
To forecast daily product demand from real sales history and convert those forecasts, plus the user's stock and lead time, into reorder recommendations, all in a working web application with no database.

**Q2. Which dataset did you use and why?**  
The UCI Online Retail dataset (541,909 real transactions of a UK online gift wholesaler, Dec 2010 – Dec 2011). It is real, public and messy, so it shows genuine data-cleaning skills.

**Q3. What are the columns?**  
InvoiceNo, StockCode, Description, Quantity, InvoiceDate, UnitPrice, CustomerID and Country.

**Q4. What is the biggest limitation of the dataset?**  
It has no stock-on-hand, lead times, purchase orders or stockout history. So current stock and lead time are entered by the user, and inventory outputs are recommendations, not historical measurements.

**Q5. What does an invoice starting with 'C' mean?**  
A cancellation. There were 9,251 such lines after removing duplicates. They are not deleted blindly; they are labelled as returns or non-product cancellations.

**Q6. How did you handle negative quantities?**  
By context. On 'C' invoices they are returns or cancellations. On normal invoices with zero price they are stock adjustments (damaged, lost): 1,336 lines. Neither counts as demand.

**Q7. What is a REVERSED_SALE?**  
A sale that a later cancellation exactly reverses (same customer, product and quantity). That order was never fulfilled, so it is not demand. 2,805 lines, including the famous 80,995-unit line.

**Q8. Did you delete outliers?**  
No. Large lines were investigated. The two extreme ones were cancelled orders (REVERSED_SALE). The other 2,289 large lines are real bulk orders, so they were flagged and kept.

**Q9. Why remove exact duplicates?**  
Rows identical in all 8 columns, down to the minute, are almost certainly double entries. Keeping them would double-count demand. 5,268 were removed.

**Q10. Why keep rows with missing CustomerID?**  
Product demand does not depend on knowing who bought. CustomerID matters only for customer analysis, so those rows are excluded only there.

**Q11. What is your forecasting target?**  
NEXT_DAY_DEMAND: units of a product sold on date D (SALE rows), predicted from information available at the end of D-1. It is gross fulfilled demand.

**Q12. Gross or net demand, and why?**  
Gross fulfilled demand. Inventory must cover what customers order; returns come back later and do not tell you how much to stock. Returns are tracked separately.

**Q13. What is a product-day panel?**  
A table with one row per product per calendar day, from the product's first to its last sale. Days without sales inside that window get 0 demand.

**Q14. Why not fill zeros before the first sale?**  
Before its first sale the product may not have been on sale yet. Treating that period as zero demand would teach the model false zeros.

**Q15. How did you treat days the shop was closed?**  
The shop never traded on Saturdays and closed for Christmas and bank holidays (69 closed dates). Those days stay as 0 in the series, so lag_7 is always the same weekday, but they are never used as training targets. Future Saturdays are forecast as 0 by an explicit rule.

**Q16. What is data leakage?**  
Using information during training that would not be available at prediction time, for example future sales. It makes results look better than they really are.

**Q17. How did you prevent leakage?**  
Sort by product and date; apply shift(1) per product before every rolling statistic; use only past prices; split by date; tune only inside the training period; and use the same feature function for training and forecasting. Unit tests check all of this.

**Q18. Explain lag_7.**  
Units sold seven days earlier, which is the same weekday last week. It captures weekly patterns.

**Q19. Explain rolling_mean_7.**  
The average units over the 7 days before D (D-7 to D-1), computed as demand.shift(1).rolling(7).mean(). It never includes day D itself.

**Q20. Why shift before rolling?**  
Without the shift, the 7-day mean on day D would include D's own demand, which is the target. That is leakage.

**Q21. How are price features safe?**  
They use only prices from earlier sales (last known price and the 28-day average). When forecasting, the last known price is held constant; no future price is used.

**Q22. How did you split the data?**  
By date: train 2011-01-04–2011-08-31 (70%), validation to 2011-10-20 (15%), test to 2011-12-09 (15%). Random splitting would let the model see the future.

**Q23. What is rolling-origin cross-validation?**  
Training data is cut into consecutive blocks. Each fold trains on earlier blocks and validates on the next one, like making a forecast at several past dates.

**Q24. Why do you need baselines?**  
To prove ML adds value. If a simple rule like the 7-day average is just as good, the complex model is not worth it.

**Q25. Which baselines did you use?**  
Previous-day demand, same day last week, and the 7-day moving average.

**Q26. Which ML models did you compare?**  
Linear Regression, Random Forest, HistGradientBoosting and XGBoost, all wrapped in scikit-learn pipelines with an imputer, plus scaling for Linear Regression.

**Q27. How does Random Forest work?**  
It builds many decision trees on random samples of rows and features and averages their predictions. Averaging reduces variance and overfitting.

**Q28. How does gradient boosting work?**  
It adds small trees one after another. Each new tree fits the errors left by the previous trees, and a learning rate controls each step.

**Q29. Why Poisson loss?**  
Demand is a non-negative count. A Poisson loss models counts naturally and is less dominated by rare huge orders than squared error. It improved validation MAE.

**Q30. Why not absolute-error loss if it gave lower MAE?**  
It predicts the median, which for intermittent demand is far below the mean, so it under-forecasts total demand badly (see the loss check). That would cause stockouts.

**Q31. How did you tune hyperparameters?**  
RandomizedSearchCV with rolling-origin folds inside the training dates, scored by MAE. The test set was never used for tuning.

**Q32. How did you select the final model?**  
The lowest validation MAE among the ML models: HistGradientBoosting.

**Q33. What is MAE?**  
Mean Absolute Error: the average absolute difference between predicted and actual units per day. It is easy to explain in business terms.

**Q34. What is RMSE?**  
Root Mean Squared Error. It squares errors before averaging, so big misses count more.

**Q35. What is WAPE and why use it?**  
Sum of absolute errors divided by total actual demand. It is a percentage that still works when many days have zero demand.

**Q36. Why is MAPE problematic here?**  
MAPE divides by the actual value, so it is undefined on zero-demand days and explodes when actuals are tiny. It is computed only on days with at least 5 units, and its coverage is shown.

**Q37. What are your final results?**  
HistGradientBoosting: test MAE 21.27, RMSE 70.55, WAPE 89.2%. On the untouched test period, HistGradientBoosting did **not** beat the best baseline (Baseline: 7-day moving average): MAE 21.275 vs 21.226 (-0.2% change). This result is reported exactly as measured.

**Q38. Your WAPE is high. Is the model bad?**  
Daily product demand in wholesale retail is very intermittent and bursty, so high day-level WAPE is normal. Weekly totals are far more stable. The important checks are the honest comparison with baselines and using measured variability for safety stock.

**Q39. Did ML beat the baseline?**  
On validation, yes (MAE 18.42 vs 21.15). On the test period: no, it essentially tied (-0.2%). This was reported exactly as measured, without tuning on the test set.

**Q40. What is recursive forecasting?**  
The model predicts one day. That prediction is added to the history and features are rebuilt to predict the next day, repeating up to 7, 14 or 30 days. Actual future demand is never used.

**Q41. Why can recursive errors grow?**  
Later days are built on predicted rather than real values, so earlier mistakes propagate. The recursive backtest measures this.

**Q42. Which features matter most?**  
rolling_mean_28, hist_mean_demand, hist_std_demand, measured by permutation importance. The hist_gradient_boosting model bases its forecast mainly on recent averages / volatility of demand (49% of total importance). rolling: 49%; history: 44%; price: 4%; calendar: 3%; lag: 0%.

**Q43. What is permutation importance?**  
Shuffle one feature on the test data and measure how much MAE gets worse. A bigger increase means the model relies on that feature more. It works for any model.

**Q44. Explain safety stock.**  
Extra stock that protects against demand variability during the lead time: SS = Z × σ_daily × √L. A higher service level or longer lead time means more safety stock.

**Q45. How do you get Z?**  
From the inverse standard normal distribution of the service level: 95% gives 1.645 and 99% gives 2.326.

**Q46. Explain reorder point and target stock.**  
ROP = d × L + SS: when stock falls to this level, order. Target T = d × (L + R) + SS covers the lead time plus the time until the next review.

**Q47. How is order quantity computed?**  
Q = max(0, T − current stock), rounded up to the MOQ and pack size, then limited by storage capacity. Any shortfall is displayed.

**Q48. How are stock statuses defined?**  
Critical when stock ≤ safety stock; Low when stock ≤ reorder point; Overstocked when stock > 1.5 × target; otherwise Healthy. One tested function is used everywhere.

**Q49. Explain ABC analysis.**  
Products are sorted by revenue and cumulative share is computed. A covers the first 80% of revenue (844 products), B the next 15%, and C the rest. Focus control effort on A items.

**Q50. Why no database, and how is data kept safe?**  
The brief requires files. Data is stored as CSV, JSON, Parquet and Joblib with atomic temp-file writes, per-file locks, schema validation, UUID record IDs and quarantine of corrupted files. History survives restarts.


## Examiner questions about dataset limitations
* **"Where did the stock values come from?"** They are entered by the user. UCI has no stock data, and the UI labels every value as
  dataset-derived, user-entered, model-predicted or calculated.
* **"Can you claim yearly seasonality?"** No. About 12 months of data contain one seasonal cycle, so we describe an observed November
  peak, not a proven yearly pattern.
* **"Are returns subtracted from demand?"** No. Gross fulfilled demand is used; returns are reported separately. Only orders that were
  cancelled in full are excluded.
* **"Why only 500 products?"** These have the longest sales history. Products with only a few sale days cannot
  support lag-28 features or reliable evaluation. The limit is configurable.
* **"Are the results realistic?"** They come from the untouched final 2011-10-21 – 2011-12-09 period,
  with no tuning on it, and they are compared with baselines.
* **"What about holidays after December 2011?"** They are unknown to the model, and the forecast page warns about Christmas.

## Future improvements
Weekly or hierarchical forecasts; Croston/TSB for intermittent demand; conformal prediction intervals; safety stock from forecast
errors and lead-time variability; holiday and promotion calendars; ERP integration; authentication; Docker; automatic retraining
and drift monitoring.
