## Download Gitter messages and parse them into an Elasticsearch index

There are two scripts: 

- gitter_content_indexer_es.py which will talk directly to an ElasticSearch instance, referred to as the "es" version
- gitter_content_indexer_as.py which will talk to an Enterprise App Search instance, referred to as the "as" version

The API is different for each hence the two scripts. Note that the "es" version has not been updated to handle authentication.

Both use the Gitter REST API to download archives of public Gitter rooms then extracts relevant data and loads them intan Elasticsearch index. 

The name of the target index is specified in the config.yaml file

The "es" version  will create the index when run the first time .

### Configuration

- Create a file called  _token_  which must contain the Gitter developer token of a user that is a member of the Gitter rooms to be indexed. 

- If backup to Github is enabled, this user must also have permissions to push to the Github archive  backup repository.

- Copy  _config.sample.yml_  to  _config.yml_  and edit with your settings (at this time the base_endpoint and api_key are not needed for the "es" version of the script):

```yaml
base_endpoint: the base URL without the protocol
api_key: obtained from the App Search web interface
index: the name of the target index
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
- elasticsearch >= 7.7.1 or elastic-app-search >= 7.7.0 depending on which script you use
- pyyaml >= 5.3.1
- gitpython >= 3.1.3

### Credits

This script is an extension of https://github.com/minrk/archive-gitter

License: CC-0, Public Domain
