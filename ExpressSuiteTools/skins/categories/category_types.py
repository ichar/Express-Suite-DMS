## Script (Python) "category_types"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=type_names=[]
##title=
##
# $Id: category_types.py,v 1.3 2003/09/26 08:45:37 ikuleshov Exp $
# $Revision: 1.3 $
req = context.REQUEST

if type_names:
    message = 'You have changed the list of allowed content types'
    context.setAllowedTypes(type_names)
else:
    message = 'You have to specify at least one content_type'

req['RESPONSE'].redirect( context.absolute_url( message=message) )

