#!/usr/bin/env python3
"""
Fetch gitter archives of all token bearer's public rooms and uploads
new entries to an instance of ElasticSearch's App Search
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
from elastic_app_search import Client
from datetime import datetime, timezone, timedelta
from dateutil.parser import parse

client = Client(
    base_endpoint='localhost:3002/api/as/v1',
    api_key='private-dwf2k2bdmawkiw265d78fc6z',
    use_https=False
)

with open('token') as f:
    token = f.read().strip()

h = {'Authorization': 'Bearer %s' % token}

with open(r'config.yml') as file:
    config = yaml.load(file, Loader=yaml.FullLoader)

engine_name = config['index']
archive_dir = config['archivedir']
archive_name = os.path.join(archive_dir, 'archive')

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
        print('Requests remaining %s' % remaining)
        if remaining < 10:
            #print("slowing down...")
            time.sleep(10)
        else:
            time.sleep(1)
    #else print('Request was cached')
    return r.json()

def extract_es_messages(indexed_messages, messages):
    num_messages = len(messages) 
    for message in messages:
        es_message = { 
            'group_name' : group_name,
            'room_name' : room_name,
            'display_name' : message['fromUser']['displayName'],
            'username' : message['fromUser']['username'],
            'message' : message['text'],
            'sent' : message['sent']
        }
        indexed_messages.append(es_message)
    print('Extracted ' + str(len(messages)) + ' messages')

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
        print('Checking for new messages: %s' % dest)
        with open(dest) as f:
            room_messages = json.load(f)
        with open(es_dest) as ff:
            indexed_messages = json.load(ff)
    else:
        print('New room: %s' % dest)
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
            print('Failed to get messages for %s: %s' % (name, e))
            continue
        
    extract_es_messages(indexed_messages, messages)
    
    while messages:
        if key == 'beforeId':
            room_messages[:0] = messages
            edge_message = messages[0]
        else:
            room_messages.extend(messages)
            edge_message = messages[-1]
        messages = gitter_api_request('/rooms/%s/chatMessages?limit=5000&%s=%s' % (
            room['id'], key, edge_message['id']))
        
        extract_es_messages(indexed_messages, messages)

    print('Total messages for this room ' + str(len(room_messages)))

    if (len(room_messages) != len(indexed_messages)):
        print('Error!: no. of room messages != indexed messages')
        sys.exit(1);

    print('Indexing documents ...')
    tot = len(indexed_messages)
    r = tot % 100
    if (tot > 100):
      ''' Can only index 100 documents at a time '''
      step = 100
      r = tot % 100
      imax = tot//100
      i = 1
      #print('r ' + str(r) + ' , imax ' + str(imax))
      while i <= imax:
        client.index_documents(engine_name, indexed_messages[(i-1)*step:(i*step)-1])
        print('Indexed %s documents' % str(step))
        i = i+1
      client.index_documents(engine_name, indexed_messages[imax*step:imax*step+r-1])
      print('Indexed %s documents' % str(r))
    else:
        client.index_documents(engine_name, indexed_messages)
        print('Indexed %s documents' % str(tot))
        
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
    
