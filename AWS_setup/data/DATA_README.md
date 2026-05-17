# Module 3 — Truck Delay CSVs

This folder must contain **exactly these 7 CSV files** before you run `deploy_m3.sh`. The deploy script syncs everything in this folder up to S3 in Step 4, and `load_csvs.py` then bulk-loads them into RDS in Step 6.

| File | Expected Size | Rows |
|------|---------------|------|
| `truck_schedule_table.csv` | ~870 KB | 12,308 |
| `trucks_table.csv` | ~35 KB | 1,301 |
| `drivers_table.csv` | ~82 KB | 1,301 |
| `routes_table.csv` | ~107 KB | 2,353 |
| `traffic_table.csv` | ~87 MB | 2,597,914 |
| `city_weather.csv` | ~3.4 MB | 55,177 |
| `routes_weather.csv` | ~28 MB | 425,713 |

**Total:** ~120 MB across the 7 files.

## If files are missing

If your repo clone arrived without these CSVs (some setups strip large files), copy them from the course's source bundle:

```
Projects Repo/Truck Delay PRoject/Part - 1/end-to-end-1/Data/Training_data/
```

Or ask your instructor for the data bundle.

## File names must match exactly

`load_csvs.py` looks up each CSV by its filename (`s3://<bucket>/data/raw/<table_name>.csv`) and uses the filename to pick the schema. Don't rename them.
