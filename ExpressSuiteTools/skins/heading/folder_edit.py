## Script (Python) "folder_edit"
##bind container=container
##bind context=context
##bind namespace=_
##bind script=script
##bind subpath=traverse_subpath
##parameters=id,title, description, nomencl_num=None, postfix=None, display_mode=None, mail_login=None, mail_password=None, mail_keep=None, mail_interval=None, mail_senders=None, mail_from_name=None, mail_from_address=None, mail_recipients=None
##title=Edit a heading
##
from Products.ExpressSuiteTools.SecureImports import refreshClientFrame

REQUEST = context.REQUEST

# test for valid id (new)
if id != context.getId():
    error = context.aq_parent.checkId( id )
    if error:
        return apply( context.folder_edit_form, (context, REQUEST),
                      script.values( portal_status_message=str(error) ) )

if mail_password is not None:
    if len(mail_password) and not len(mail_password.replace('*', '')):
      mail_password = None

    elif mail_password != REQUEST['mail_password2']:
      return apply( context.folder_edit_form, (context, REQUEST), # TODO
              script.values( portal_status_message = "Passwords do not match." ) )

context.edit( title=title, description=description )

context.setNomenclativeNumber( nomencl_num )

context.setPostfix( postfix )

if display_mode is not None and not display_mode:
    context.setMainPage( None )

if REQUEST.has_key('maxNumberOfPages'):
    context.setMaxNumberOfPages( int(REQUEST['maxNumberOfPages']) )

if REQUEST.has_key('varchive_settings'):
    context.setArchiveProperty( REQUEST['varchive_settings'] )

if REQUEST.has_key('allowed_categories'):
    context.setAllowedCategories( map(lambda x : context.portal_metadata.getCategoryById(x), REQUEST['allowed_categories']) )
elif not REQUEST.has_key('category_inheritance'):
    return apply( context.folder_edit_form, (context, REQUEST), # TODO
            script.values( portal_status_message = "Select one or more allowed categories first." ) )
else:
    context.setAllowedCategories( [] )

if REQUEST.has_key('category_inheritance'):
    context.setCategoryInheritance(1)
else:
    context.setCategoryInheritance(0)

props = {}

props['mail_password'] = mail_password

if mail_senders is not None:
    props['mail_senders'] = mail_senders.replace(',', ' ').split()

if mail_recipients is not None:
    props['mail_recipients'] = mail_recipients.replace(',', ' ').split()

context.manage_changeProperties( REQUEST, **props )

if id and id != context.getId():
    context.aq_parent.manage_renameObject( context.getId(), id )

refreshClientFrame( [ 'workspace', 'navTree' ] )

return context.redirect( frame='inFrame', message="Folder changed" )
