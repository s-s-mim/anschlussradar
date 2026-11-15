# API (phase 4)

Public HTTP API, deployed as its own Function App in Germany West Central, so every
request with user data is processed in Germany. Routes (prefix `/api/v1`):

| Route | Purpose |
| --- | --- |
| `GET /stations?q=` | Typo-tolerant station search |
| `GET /journeys?from=&to=&time=&arriveBy=&sort=&rail=` | Connections with reliability per transfer |
| `GET /model/status` | Model stage for the learning banner |
| `POST /contact` | Contact form, sent by e-mail through Azure Communication Services |
| `GET /health` | Station count, model stage, Transitous requests today |

The handlers are in `src/anschlussradar/api/service.py`; `function_app.py` only maps HTTP.
