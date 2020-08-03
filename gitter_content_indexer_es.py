#!/usr/bin/env python3
"""
Fetch gitter archives of all token bearer's public rooms and uploads
new entries to an instance of ElasticSearch
"""
import yaml
import json
import os
import sys
import time
import uuid
import requests
import requests_cache
from git import Repo
from elasticsearch import Elasticsearch
from elasticsearch.helpers import streaming_bulk
from datetime import datetime, timezone, timedelta
from dateutil.parser import parse

client = Elasticsearch('http://localhost:9200')

with open('token') as f:
    token = f.read().strip()

h = {'Authorization': 'Bearer %s' % token}

with open(r'config.yml') as file:
    config = yaml.load(file, Loader=yaml.FullLoader)
archive_dir = config['archivedir']
archive_name = os.path.join(archive_dir, 'archive')
index_name = config['index_name']
requests_cache.install_cache(archive_dir + '/gitter_indexer')

def utcnow():
    return datetime.now(timezone.utc)

def gitter_api_request(path):
    request_time = utcnow()
    if not path.startswith('/'):
        path = '/' + path
    r = requests.get('https://api.gitter.im/v1' + path, headers=h)
    r.raise_for_status()
    if parse(r.headers['date']) + timedelta(minutes=10) > request_time:
        # if not a cached response, slow down:
        remaining = int(r.headers['X-RateLimit-Remaining'])
        #print("Requests remaining: %s" % remaining)
        if remaining < 10:
            print("slowing down...")
            time.sleep(10)
        else:
            time.sleep(1)
    #else print("Request was cached")
        
    return r.json()

def create_index(client):
    """Creates an index in Elasticsearch if one isn't already there."""
    client.indices.create(
        index=index_name,
        body={
            "settings": {"number_of_shards": 1},
            "mappings": {
                "properties": {
                    "group_name": { "type": "keyword" },
                    "room_nameame": { "type": "keyword" },
                    "display_name": { "type": "text" },
                    "username": { "type": "keyword" },
                    "message": { "type": "text" },
                    "sent": { "type": "date", "format": "date_optional_time" },
                    "gitter_id": { "type": "text"}
                }
            },
        }
    )
    
def linkifyId(group_name, room_name, gitterId):
        link = 'https://gitter.im/' 
        if (group_name != 'None'):
            link = link + group_name + "/"
        link = link + room_name + "?at=" + gitterId
        return link

def extract_es_messages(indexed_messages, messages):
    for message in messages:
        es_message = { 
            'group_name' : group_name,
            'room_name' : room_name,
            'display_name' : message['fromUser']['displayName'],
            'username' : message['fromUser']['username'],
            'message' : message['text'],
            'sent' : message['sent'],
            'gitter_id' : linkifyId(group_name, room_name, message['id'])
        }
        indexed_messages.append(es_message)
        yield es_message
        
def index_messages(indexed_messages, messages):
    num_messages = len(messages) 
    successes = 0
    for ok, action in streaming_bulk( client=client, index=index_name, actions=extract_es_messages(indexed_messages, messages)):
        successes += ok
    if (successes != num_messages):
        print('Warning!: only %d/%d messages were indexed' % (successes, num_messages))
    print('Processed ' + str(len(messages)) + ' messages')

# Get list of indexes and check that the Gitter index exists.
# If it does not, create it
r = requests.get('http://localhost:9200/_aliases')
r.raise_for_status()
indexes = r.json().keys()
if ( index_name not in indexes):
    print('Creating index "gitter-index"')
    create_index(client)

# Get the data from Gitter
rooms = gitter_api_request('/rooms?_=%s' % uuid.uuid4().hex)

for room in rooms:
    name = room['name']
    print('Processing: ' + name)
    group_name = 'None'
    room_name = ''
    if '/' in name:
        group_name = name.rsplit('/', 1)[0]
        room_name = name.rsplit('/', 1)[1]
        
    # We do not archive one to one or private conversations (the latter could be configurable)
    if room['oneToOne'] or room.get('security') == 'PRIVATE':
        continue
    
    uri = room.get('uri', room['url'].lstrip('/'))
    dest = os.path.join(archive_name, uri + '.json')
    es_dest = os.path.join(archive_name, uri + '_es.json')
    if '/' in dest:
        d = dest.rsplit('/', 1)[0]
        if not os.path.exists(d):
            os.makedirs(d)

    if os.path.exists(dest):
        print("Checking for new messages: %s" % dest)
        with open(dest) as f:
            room_messages = json.load(f)
        with open(es_dest) as ff:
            indexed_messages = json.load(ff)
    else:
        print("New room: %s" % dest)
        room_messages = []
        indexed_messages = []
        
    if room_messages:
        key='afterId'
        last_id = room_messages[-1]['id']
        messages = gitter_api_request('/rooms/%s/chatMessages?limit=5000&afterId=%s&_=%s' % (
            room['id'], room_messages[-1]['id'], uuid.uuid4().hex))
    else:
        key='beforeId'
        try:
            messages = gitter_api_request('/rooms/%s/chatMessages?limit=5000&' % room['id'])
        except Exception as e:
            print("Failed to get messages for %s: %s" % (name, e))
            continue
        
    if (config['index']):
        index_messages(indexed_messages, messages)
    
    while messages:
        if key == 'beforeId':
            room_messages[:0] = messages
            edge_message = messages[0]
        else:
            room_messages.extend(messages)
            edge_message = messages[-1]
        messages = gitter_api_request('/rooms/%s/chatMessages?limit=5000&%s=%s' % (
            room['id'], key, edge_message['id']))
        
        if (config['index']):
            index_messages(indexed_messages, messages)
            
    print('Total messages for this room ' + str(len(room_messages)))
    
    if (len(room_messages) != len(indexed_messages)):
        print('Error!: no. of room messages != indexed messages')
        sys.exit(1);
        
    print('Saving messages to disk ...')
    with open(dest, 'w') as f:
        json.dump(room_messages, f, sort_keys=True, indent=1)
    with open(es_dest, 'w') as ff:
        json.dump(indexed_messages, ff, sort_keys=False, indent=1)
        
if (config['archive']):
    print('Backing up messages...')
    now = datetime.now()
    untracked = []
    dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
    try:
        repo = Repo(archive_dir)
        untracked = repo.untracked_files
        if (len(untracked) > 0):
            repo.index.add(untracked)
            repo.index.commit('Initial commit ' + dt_string)
        
        repo.git.add(all=True)
        repo.index.commit('Message index update ' + dt_string)
            
        origin = repo.remote(name='origin')
        origin.push()
        print('\nSuccessfully pushed to backup Github repo')    
    except Exception as e:
        print('Error while backing up to github: %s' % e)    
    
