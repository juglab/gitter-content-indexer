# Downloads Gitter messages and parses them into Elasticsearch index

- Uses the Gitter REST API to download archives of public Gitter rooms.

- Extracts relevant data and loads it into Elasticsearch engine (will create index
when run the first time)

- Copies of the ingested data are also saved to `archive/group/room.json`

- Requires a Gitter API token saved to the file `token`

- Schedule runs with crontab, will check for new messages since last run.

## Requirements

- Pythin 3.7
- requests
- requests_cache
- python-dateutil
- elasticsearch