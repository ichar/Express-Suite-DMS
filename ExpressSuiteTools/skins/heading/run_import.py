## Script (Python) "run_import"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=file,ownership=None
##title=Run Import
##
REQUEST = context.REQUEST
RESPONSE = context.REQUEST.RESPONSE

#get first non-version
object = context

message = None
if not file:
    message = "You should type file name for import"
else:
    try:
        f = object.manage_importObject( file=file, REQUEST=None, set_owner=ownership )
    except:
        message = "Object was not imported"
if not message:
    message = "Object was successfully imported"

RESPONSE.redirect( context.absolute_url( message=message ) )