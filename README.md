## Downloads Gitter messages and parses them into an Elasticsearch index

Uses the Gitter REST API to download archives of public Gitter rooms then extracts relevant data and loads it into Elasticsearch engine. 
The will create the index  _gitter-index_  when run the first time.

### Configuration

- Create a file called  _token_  which must contain the Gitter developer token of a user that is a member of the Gitter rooms to be indexed. 

- If backup to Github is enabled, this user must also have permissions to push to the Github archive  backup repository.

- In the  _config.yml_  file specify:

```yaml
archive: True if want to push saved data to a git repo
archivedir: path to where script will write data to
```

### Data archive

The script saves copies of both the Gitter data and the Elasticsearch indexed data to `<archivedir>/archive/<group>/<room>.json` and `<archivedir>/archive/<group>/<room>_es.json` respectively.

### Backing up to Github

If  _archive_  is set to True in  _config.yml_  and  _archivedir_  is a git(hub) repository directory then the script will commit and push the archived data to Github at the end of a run.


### Requirements

- Python 3.7
- requests
- requests_cache
- python-dateutil
- json
- elasticsearch == 7.7.1
- pyyaml == 5.3.1
- gitpython >= 3.1.3

### Credits

This script is an extension of https://github.com/minrk/archive-gitter

License: CC-0, Public Domain
