Resource-to-Collection
======================

usage: resource_to_collection.py [-h] -r RESOURCE [-c COLLECTION] [-s SPACE]
                                 [-u UNIQNAME]
                                 {create,update}

Create or update a DSpace Collection from an ArchivesSpace Resource (also
creates an Archivematica Storage Service Location for the DSpace Collection,
creates and links an ArchivesSpace Digital Object for the DSpace Collection to
the ArchivesSpace Resource, and notifies the processor via a message on
Slack).

positional arguments:
  {create,update}       either create or update

optional arguments:
  -h, --help            show this help message and exit
  -r RESOURCE, --resource RESOURCE
                        an archivesspace resource (source of collection
                        metadata)
  -c COLLECTION, --collection COLLECTION
                        a dspace collection (to be created or updated)
  -s SPACE, --space SPACE
                        an archivematica storage service space (to which a
                        location will be added)
  -u UNIQNAME, --uniqname UNIQNAME
                        the uniqname (of processor)

Sample config.ini file:

```
[archivesspace]
base_url = http://141.211.39.87:8089
user = eckardm
password = password
repository = 2

[dspace]
base_url = https://dev.deepblue.lib.umich.edu
email = eckardm@umich.edu
password = password
community_id = 35

[archivematica_storage_service]
url = http://rumble.umdl.umich.edu:8000
username = eckardm
password = password

[slack]
token = token
```
