# Stage 1 — Dataset Overview Report
_Generated: 2026-11-14T17:09:10Z — all numbers computed from the actual file; nothing is assumed._
## 1. File
> Confirms which file was analysed (name, size, SHA-256 fingerprint) so results are reproducible.
- File: `Online Retail.xlsx` (22.62 MB)
- SHA-256: `43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16ae4c3936424676d`
## 2. Dimensions
> Shows how big the dataset is: rows = invoice lines, columns = attributes.
- Rows: **541,909**
- Columns: **8**
## 3. Columns and data types
> Lists every column with its data type, meaning, missing values and number of distinct values.
| name | dtype | non_null | missing | missing_pct | unique | description |
|---|---|---|---|---|---|---|
| InvoiceNo | string | 541909 | 0 | 0 | 25900 | Invoice number. A 6-digit number per transaction; a leading 'C' means the invoice was cancelled. |
| StockCode | string | 541909 | 0 | 0 | 4070 | Product (item) code that uniquely identifies a product. |
| Description | string | 540455 | 1454 | 0.268 | 4211 | Product name / description text. |
| Quantity | Int64 | 541909 | 0 | 0 | 722 | Number of units of the product on that invoice line. Negative values indicate returns/cancellations. |
| InvoiceDate | datetime64[ns] | 541909 | 0 | 0 | 23260 | Date and time when the invoice was generated. |
| UnitPrice | float64 | 541909 | 0 | 0 | 1630 | Price per unit in pounds sterling (GBP). |
| CustomerID | Int64 | 406829 | 135080 | 24.93 | 4372 | 5-digit customer identifier. Missing for some (often guest) transactions. |
| Country | string | 541909 | 0 | 0 | 38 | Country where the customer resides. |

## 4. Type conversion check
> Reports values that could not be converted to the correct type (e.g. text in a number column).
| column | missing_before | invalid_coerced |
|---|---|---|
| InvoiceNo | 0 | 0 |
| StockCode | 0 | 0 |
| Description | 1454 | 0 |
| Country | 0 | 0 |
| Quantity | 0 | 0 |
| CustomerID | 135080 | 0 |
| UnitPrice | 0 | 0 |
| InvoiceDate | 0 | 0 |

## 5. First five rows
> The first five rows: a quick look at what the raw data looks like.
| InvoiceNo | StockCode | Description | Quantity | InvoiceDate | UnitPrice | CustomerID | Country |
|---|---|---|---|---|---|---|---|
| 536365 | 85123A | WHITE HANGING HEART T-LIGHT HOLDER | 6 | 2010-12-01T08:26:00 | 2.55 | 17850 | United Kingdom |
| 536365 | 71053 | WHITE METAL LANTERN | 6 | 2010-12-01T08:26:00 | 3.39 | 17850 | United Kingdom |
| 536365 | 84406B | CREAM CUPID HEARTS COAT HANGER | 8 | 2010-12-01T08:26:00 | 2.75 | 17850 | United Kingdom |
| 536365 | 84029G | KNITTED UNION FLAG HOT WATER BOTTLE | 6 | 2010-12-01T08:26:00 | 3.39 | 17850 | United Kingdom |
| 536365 | 84029E | RED WOOLLY HOTTIE WHITE HEART. | 6 | 2010-12-01T08:26:00 | 3.39 | 17850 | United Kingdom |

## 6. Last five rows
> The last five rows: confirms the file was read to the end and shows the latest records.
| InvoiceNo | StockCode | Description | Quantity | InvoiceDate | UnitPrice | CustomerID | Country |
|---|---|---|---|---|---|---|---|
| 581587 | 22613 | PACK OF 20 SPACEBOY NAPKINS | 12 | 2011-12-09T12:50:00 | 0.85 | 12680 | France |
| 581587 | 22899 | CHILDREN'S APRON DOLLY GIRL | 6 | 2011-12-09T12:50:00 | 2.1 | 12680 | France |
| 581587 | 23254 | CHILDRENS CUTLERY DOLLY GIRL | 4 | 2011-12-09T12:50:00 | 4.15 | 12680 | France |
| 581587 | 23255 | CHILDRENS CUTLERY CIRCUS PARADE | 4 | 2011-12-09T12:50:00 | 4.15 | 12680 | France |
| 581587 | 22138 | BAKING SET 9 PIECE RETROSPOT | 3 | 2011-12-09T12:50:00 | 4.95 | 12680 | France |

## 7. Random sample (seed 42)
> Five random rows (fixed seed 42, so reproducible) to see typical records from the middle of the file.
| InvoiceNo | StockCode | Description | Quantity | InvoiceDate | UnitPrice | CustomerID | Country |
|---|---|---|---|---|---|---|---|
| 555200 | 71459 | HANGING JAM JAR T-LIGHT HOLDER | 24 | 2011-06-01T12:05:00 | 0.85 | 17315 | United Kingdom |
| 554974 | 21128 | GOLD FISHING GNOME | 4 | 2011-05-27T17:14:00 | 6.95 | 14031 | United Kingdom |
| 550972 | 21086 | SET/6 RED SPOTTY PAPER CUPS | 4 | 2011-04-21T17:05:00 | 0.65 | 14031 | United Kingdom |
| 576652 | 22812 | PACK 3 BOXES CHRISTMAS PANETTONE | 3 | 2011-11-16T10:39:00 | 1.95 | 17198 | United Kingdom |
| 546157 | 22180 | RETROSPOT LAMP | 2 | 2011-03-10T08:40:00 | 9.95 | 13502 | United Kingdom |

## 8. Statistical summary (numeric)
> Count, mean, standard deviation, min/max and percentiles of numeric columns. Negative or extreme values here hint at returns and outliers.
| statistic | Quantity | UnitPrice |
|---|---|---|
| count | 5.419e+05 | 5.419e+05 |
| mean | 9.552 | 4.611 |
| std | 218.1 | 96.76 |
| min | -8.1e+04 | -1.106e+04 |
| 1% | -2 | 0.19 |
| 5% | 1 | 0.42 |
| 25% | 1 | 1.25 |
| 50% | 3 | 2.08 |
| 75% | 10 | 4.13 |
| 95% | 29 | 9.95 |
| 99% | 100 | 18 |
| max | 8.1e+04 | 3.897e+04 |
| negative_count | 10624 | 2 |
| zero_count | 0 | 2515 |

## 9. Statistical summary (text columns)
> Most frequent value and number of distinct values for text columns.
| column | count | unique | top | top_frequency |
|---|---|---|---|---|
| InvoiceNo | 541909 | 25900 | 573585 | 1114 |
| StockCode | 541909 | 4070 | 85123A | 2313 |
| Description | 540455 | 4211 | WHITE HANGING HEART T-LIGHT HOLDER | 2369 |
| Country | 541909 | 38 | United Kingdom | 495478 |

## 10. Date range
> First and last transaction timestamps and how many days the data covers.
- First transaction: **2010-12-01T08:26:00**
- Last transaction: **2011-12-09T12:50:00**
- Calendar span: **374 days**; days with at least one transaction: **305**
- Months covered: 2010-12, 2011-01, 2011-02, 2011-03, 2011-04, 2011-05, 2011-06, 2011-07, 2011-08, 2011-09, 2011-10, 2011-11, 2011-12

## 11. Missing values
> How many values are empty in each column. Missing CustomerID matters for customer analysis but not for product demand.
| column | missing | missing_pct |
|---|---|---|
| InvoiceNo | 0 | 0 |
| StockCode | 0 | 0 |
| Description | 1454 | 0.268 |
| Quantity | 0 | 0 |
| InvoiceDate | 0 | 0 |
| UnitPrice | 0 | 0 |
| CustomerID | 135080 | 24.93 |
| Country | 0 | 0 |

Rows with at least one missing value: **135,080**

## 12. Duplicates
> Rows that are exact copies across all 8 columns. They may be data-entry duplicates and are reviewed in Stage 3.
- Extra exact-duplicate rows (beyond first copy): **5,268** (0.972%)
- Distinct duplicated records: **4,879**

## 13. Unique counts
> Number of distinct products, customers, invoices and countries.
| entity | unique |
|---|---|
| products_stockcode | 4070 |
| descriptions | 4211 |
| customers | 4372 |
| invoices | 25900 |
| cancelled_invoices | 3836 |
| countries | 38 |

## 14. Early data-quality observations
> Early warning signs (cancellations, negative quantities, zero prices, non-product codes). Observed only; handled in Stage 3.
| observation | rows |
|---|---|
| cancellation_rows_invoice_starts_with_C | 9288 |
| negative_quantity_rows | 10624 |
| negative_quantity_rows_not_cancelled | 1336 |
| zero_quantity_rows | 0 |
| zero_unit_price_rows | 2515 |
| negative_unit_price_rows | 2 |
| missing_customer_id_rows | 135080 |
| missing_description_rows | 1454 |
| non_standard_stockcode_rows | 2995 |
| stockcodes_with_multiple_descriptions | 647 |

Most frequent non-standard StockCodes (postage, fees, manual adjustments, etc.):

| StockCode | rows |
|---|---|
| POST | 1256 |
| DOT | 710 |
| M | 571 |
| C2 | 144 |
| D | 77 |
| S | 63 |
| BANK CHARGES | 37 |
| AMAZONFEE | 34 |
| CRUK | 16 |
| DCGSSGIRL | 13 |
| DCGSSBOY | 11 |
| gift_0001_20 | 10 |
| gift_0001_10 | 9 |
| gift_0001_30 | 8 |
| DCGS0003 | 5 |

## 15. Comparison with UCI documentation
> Compares what we actually found with what UCI documents, without assuming either is correct.
| property | documented | observed | match |
|---|---|---|---|
| rows | 541909 | 541909 | True |
| columns | 8 | 8 | True |
| period | 2010-12 to 2011-12 | 2010-12 to 2011-12 | True |
