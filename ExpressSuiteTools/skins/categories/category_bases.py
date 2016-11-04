## Script (Python) "category_bases"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=bases=[]
##title=
##
# $Id: category_bases.py,v 1.1 2003/09/26 08:45:37 ikuleshov Exp $
# $Revision: 1.1 $
REQUEST = context.REQUEST

message = ''
if not REQUEST.get('cancel'):
    message = 'You have changed the list of base categories'
    context.setBases([context.getCategoryById(x) for x in bases])

REQUEST['RESPONSE'].redirect( context.absolute_url(message=message) )
