# Downloads Gitter messages and parses them into Elasticsearch index

- Uses the Gitter REST API to download archives of public Gitter rooms.

- Extracts relevant data and loads it into Elasticsearch engine (will create index
when run the first time)

- Copies of the ingested data are also saved to `archive/group/room.json`

- Path to archive directory must be specified in the config.yml file

- Requires a Gitter API token saved to the file `token`. The token owner must be 
  a member of the room(s) we want to index. 

- Schedule runs with crontab, will check for new messages since last run.

- If the archive directory is in a git directory the script will commit and push to origin. 

## Requirements

- Pythin 3.7
- requests
- requests_cache
- python-dateutil
- elasticsearch
- json
- pyyaml
- git