## Script (Python) "run_export"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=type,id=None,download=None,xml=None
##title=Run Export
##
REQUEST = context.REQUEST
RESPONSE = context.REQUEST.RESPONSE

#get first non-version
object = context

message = None
try:
    if type == 'folder':
        while not ( id in object.objectIds() or object.implements('isPortalRoot') ):
            object = object.aq_parent
        f = object.manage_exportObject( id=id, download=download, toxml=xml, RESPONSE=RESPONSE, REQUEST=REQUEST )
    else:
        f = object.manage_exportObject( id=None, download=download, toxml=xml, RESPONSE=RESPONSE, REQUEST=REQUEST )
except:
    message = "Object was not exported"
if not message:
    message = "Object was successfully exported"

if not download:
    RESPONSE.redirect( context.absolute_url( message=message ) )