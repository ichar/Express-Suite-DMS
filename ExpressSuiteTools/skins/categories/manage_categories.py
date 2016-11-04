## Script (Python) "manage_categories"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=
##title=Change allowed subjects for the given content type
##
# $Id: manage_categories.py,v 1.3.10.1 2004/01/05 11:59:04 kfirsov Exp $
# $Revision: 1.3.10.1 $

from Products.ExpressSuiteTools.SecureImports import DuplicateIdError

message = 'Changes saved'

REQUEST=context.REQUEST
if REQUEST.has_key('addCategory'):
   #Adding new category
   category_id = REQUEST['category_id']
   category_title = REQUEST['category_title']

   try:
       context.portal_metadata.addCategory(cat_id=category_id, title=category_title)
   except DuplicateIdError, error:
       return apply( context.manage_categories_form, (context, REQUEST),
                  script.values( use_default_values=1, portal_status_message=str(error) ) )


if REQUEST.has_key('deleteCategories'):
   #Deleting categories
   selected_categories = REQUEST.get('selected_categories')
   message = context.portal_metadata.deleteCategories(selected_categories)

REQUEST['RESPONSE'].redirect( context.absolute_url(action='manage_categories_form', message=message))
