Resource-to-Collection
======================

usage: resource_to_collection.py [-h] -r RESOURCE {create,update}

Create or update a DSpace collection from an ArchivesSpace resource.

positional arguments:
  {create,update}       either create or update

optional arguments:
  -h, --help            show this help message and exit
  -r RESOURCE, --resource RESOURCE
                        an archivesspace resource
                        
If you select create, Resource-to-Collection will:
  * parse the ArchivesSpace Resource ID;
  * get the ArchivesSpace Resource;
  * check to see if a ArchivesSpace Digital Object Instance exists, and if not...
  * create a DSpace Collection from a template (introductory_text.txt) and the ArchivesSpace Resource;
  * post the DSpace Collection;
  * update the "View all items in this collection" button;
  * create an ArchivesSpace Digital Object; and 
  * link the ArchivesSpace Digital Object to the ArchivesSpace Resource.

If you select update, Resource-to-Collection will:
  * parse the ArchivesSpace Resource ID;
  * get the ArchivesSpace Resource;
  * update the DSpace Collection from a template (introductory_text.txt) and the updated ArchivesSpace Resource;
  * get the DSpace Collection Handle from the ArchivesSpace Digital Object linked to the ArchivesSpace Resource;
  * pur the DSpace Collection; and
  * update the ArchivesSpace Digital Object.
