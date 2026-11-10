# Machine learning

The code is in `src/anschlussradar/ml/`:

| File | Purpose |
| --- | --- |
| `features.py` | The one feature definition, used by training and the API |
| `metrics.py` | ROC AUC, Brier score, calibration error in plain Python |
| `stages.py` | Release stages (live_only, early, full) and the promotion rule |
| `registry.py` | Model files in a local folder, Blob Storage or a public URL |
| `train.py` | Weekly run: history, weekly split, model selection, calibration, decision |
| `export.py` | Training data from Data Explorer to Parquet |
| `serving.py` | Hourly model refresh, scores, live check and the status endpoint |

The KQL side is in `kql/00_shared.kql` (generated) and `kql/04_ml.kql`. The method and the criteria for each stage are in section 7 of the project documentation.
