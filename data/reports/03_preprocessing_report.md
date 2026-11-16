# Stage 3 — Preprocessing Report

_Generated 2026-11-14T17:16:02Z from the real dataset._

## Forecasting target policy

Gross fulfilled demand: daily sum of Quantity over SALE rows per StockCode. Returns/cancellations are tracked separately and NOT subtracted; sale lines fully reversed by a matching cancellation (REVERSED_SALE) are excluded because they were never fulfilled.

## Row accounting

| Item | Rows |
|---|---|
| original rows | 541,909 |
| missing value cells total | 136,534 |
| duplicate rows removed | 5,268 |
| rows after deduplication | 536,641 |
| invalid rows | 0 |
| cancellation lines | 9,251 |
| cancelled invoices | 3,836 |
| return lines | 8,668 |
| reversed sale lines | 2,805 |
| stock adjustment lines | 1,336 |
| accounting adjustment lines | 3 |
| non product lines | 2,354 |
| zero price lines | 1,157 |
| removed rows total | 22,174 |
| retained sale rows | 519,735 |
| missing customer id in sales | 131,387 |
| descriptions filled from stockcode | 1,341 |
| descriptions standardised | 8,621 |
| extreme quantity lines flagged kept | 2,289 |

Final cleaned dataset: **519,735 rows x 11 columns**.

## Transaction types

| Type | Rows | Revenue (GBP) | Meaning |
|---|---|---|---|
| SALE | 519,735 | 9,823,459.37 | Real fulfilled product sale (positive quantity and price). Used for demand and revenue. |
| REVERSED_SALE | 2,805 | 423,759.95 | Sale cancelled in full later by the same customer (same product and quantity). Excluded from demand. |
| RETURN | 8,668 | -475,901.16 | Product line on a cancellation ('C') invoice: goods returned/cancelled. Tracked separately. |
| CANCELLATION_NON_PRODUCT | 583 | -418,078.57 | Cancellation line for discounts, postage, fees. Not product demand. |
| STOCK_ADJUSTMENT | 1,336 | 0.00 | Negative quantity with zero price on a normal invoice (damaged, lost, stock checks). |
| ACCOUNTING_ADJUSTMENT | 3 | -11,062.06 | Bad-debt adjustment invoices starting with 'A'. Not sales. |
| NON_PRODUCT | 2,354 | 383,829.42 | Postage, carriage, bank charges, marketplace fees, manual lines, gift vouchers. |
| ZERO_PRICE | 1,157 | 0.00 | Positive quantity with zero price: no revenue, often samples or data fixes. |
| INVALID | 0 | 0.00 | Missing/invalid timestamp, StockCode or quantity. |

## Revenue definitions

- Gross fulfilled sales revenue (SALE): **£9,823,459.37**
- Gross invoiced revenue incl. reversed orders: £10,247,219.32
- Value of cancellations and returns: £-893,979.73
- Net revenue after cancellations: £9,353,239.59
- Dashboard 'revenue' = gross fulfilled sales revenue (SALE rows). Net revenue is shown separately.

## Outlier investigation

Flag if quantity > product's 99th percentile AND >= 10x product median AND >= 100 units. Flagged rows are KEPT.

Largest reversed sales (excluded because they were cancelled in full):

| Invoice | StockCode | Description | Qty | Date |
|---|---|---|---|---|
| 581483 | 23843 | PAPER CRAFT , LITTLE BIRDIE | 80,995 | 2011-12-09T09:15:00 |
| 541431 | 23166 | MEDIUM CERAMIC TOP STORAGE JAR | 74,215 | 2011-01-18T10:01:00 |
| 540815 | 21108 | FAIRY CAKE FLANNEL ASSORTED COLOUR | 3,114 | 2011-01-11T12:55:00 |
| 540815 | 21175 | GIN + TONIC DIET METAL SIGN | 2,000 | 2011-01-11T12:55:00 |
| 540815 | 85123A | WHITE HANGING HEART T-LIGHT HOLDER | 1,930 | 2011-01-11T12:55:00 |

Largest flagged (kept) sale lines:

| Invoice | StockCode | Description | Qty | Price |
|---|---|---|---|---|
| 573008 | 84077 | WORLD WAR 2 GLIDERS ASSTD DESIGNS | 4,800 | 0.21 |
| 554868 | 22197 | POPCORN HOLDER | 4,300 | 0.72 |
| 544612 | 22053 | EMPIRE DESIGN ROSETTE | 3,906 | 0.82 |
| 560599 | 18007 | ESSENTIAL BALM 3.5G TIN IN ENVELOPE | 3,186 | 0.06 |
| 550461 | 21108 | FAIRY CAKE FLANNEL ASSORTED COLOUR | 3,114 | 2.1 |
| 573995 | 16014 | SMALL CHINESE STYLE SCISSOR | 3,000 | 0.32 |
| 536830 | 84077 | WORLD WAR 2 GLIDERS ASSTD DESIGNS | 2,880 | 0.18 |
| 562439 | 84879 | ASSORTED COLOUR BIRD ORNAMENT | 2,880 | 1.45 |
| 554272 | 21977 | PACK OF 60 PINK PAISLEY CAKE CASES | 2,700 | 0.42 |
| 543057 | 84077 | WORLD WAR 2 GLIDERS ASSTD DESIGNS | 2,592 | 0.21 |

## Steps

1. Removed exact duplicate rows (identical in all 8 columns).
2. Labelled every row with one TransactionType (see transaction_types).
3. Matched cancellations to the sales they fully reverse (same customer, product, quantity).
4. Standardised descriptions: one canonical upper-case description per StockCode; missing descriptions filled from the same StockCode.
5. Kept only SALE rows in the cleaned sales dataset; computed Revenue = Quantity x UnitPrice.
6. Flagged (did not delete) extreme quantities for investigation.
7. Built a product catalog from cleaned sales.
