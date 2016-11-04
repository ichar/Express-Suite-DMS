## Script (Python) "appboardFactory"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=REQUEST, RESPONSE, id
##title=
##
# Import a standard function, and get the HTML request and response objects.
from Products.PythonScripts.standard import html_quote

request = container.REQUEST
RESPONSE = request.RESPONSE

context.invokeFactory( id=id, type_name='AppBoard Item' )

context[id].manage_permission('View', ['Anonymous', 'Member', 'Owner','Manager'], 1)

context.REQUEST.RESPONSE.redirect( context.absolute_url() + '/' + id + '/appboarditem_edit_form' )
