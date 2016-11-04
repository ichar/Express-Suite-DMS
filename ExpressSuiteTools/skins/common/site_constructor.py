## Script (Python) "site_constructor"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=id, repository_url, skin_id, title='', skin_links=[], storage_id='storage', sync_addr='', sync_path='', plugins=[]
##title=
##
# $Id: site_constructor.py,v 1.11 2003/10/13 07:08:03 inemihin Exp $
# $Revision: 1.11 $

from Products.ExpressSuiteTools.SecureImports import refreshClientFrame

error = context.checkId( id )
if error:
    return apply( context.site_constructor_form, (context, context.REQUEST),
         script.values( portal_status_message=str(error) ) )

context.manage_addProduct['ExpressSuiteTools'].manage_addSiteContainer(
	id		= id,
	title		= title,
	skin_links	= skin_links,
	storage_id	= storage_id,
	repository_url	= repository_url,
	sync_addr	= sync_addr,
	sync_path	= sync_path,
	skin_id		= skin_id,
	plugins		= plugins,
    )

refreshClientFrame( 'navTree' )
refreshClientFrame( 'workspace' )

return context[ id ].redirect( action='folder_contents', message="Site added" )
