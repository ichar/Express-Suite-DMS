## Script (Python) "document_edit"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=text_format=None, text=None, SafetyBelt='', poll='', file='', doc_type=None, deletefile=None, pastefile=None, attachfile=None, associatefile=None, rm_associate=None, id=None, upload=None, log_message='', try_to_associate=None, paste=0, IsEditFieldsOnly=0, using_fine_reader=None, unlockfile=None, lockfile=None
##title=Edit a document
##
from Products.ExpressSuiteTools.SecureImports import DateTime, SimpleError, ResourceLockedError, \
     BeginThread, CommitThread, UpdateRequestRuntime, ObjectHasCustomCategory

REQUEST = context.REQUEST

start_time = DateTime()
member = context.portal_membership.getAuthenticatedMember()
username = member.getUserName()
message = ''
action = ''

frame = context.meta_type == 'HTMLCard' and 'card_frame' or 'document_frame'

BeginThread( context, 'document_edit', force=1 )

MAX_OBJECT_SIZE = context.portal_properties.getProperty( 'max_object_size', 1048576 * 2 )

IsManager = member and member.has_role('Manager') and 1 or 0
ObjectIsLocked = 0

if not context.isCurrentVersionEditable():
    message = ( "Current version is not editable. "
                "Be sure you are editing the last (editable) version. "
                "(You may be able to recover your changes using the browser 'back' button.)")
    action = 'edit'
    """
    return REQUEST.RESPONSE.redirect(
            context.absolute_url( redirect=1, action=action, message=message, frame=frame ),
            status=303 )
    """
    context.redirect( action=action, message=message, frame=frame )

version = context.getEditableVersion()
document = version.aq_parent
category = document.Category()

try:
    if text is not None:
        document.edit( text_format, text, file, safety_belt=SafetyBelt )
        message = "Document saved."
        action = 'text'

    elif attachfile and upload and upload.filename:
        upload.seek(0,2)
        len_file = upload.tell()
        action = context.getTypeInfo().getActionById( 'attachments' )
        if context.getContentsSize() + len_file > MAX_OBJECT_SIZE and not IsManager:
            message = 'Extra file uploading is not allowed. $ (max %dMb) $ error' % ( MAX_OBJECT_SIZE / 1024 / 1024)
            """
            return REQUEST.RESPONSE.redirect(
                context.absolute_url( redirect=1, action=action, message=message, frame=frame ),
                status=303 )
            """
            context.redirect( action=action, message=message, frame=frame )

        try:
            context.addFile( id, file=upload, paste=paste, try_to_associate=try_to_associate )
        except SimpleError, message:
            """
            return apply( getattr(context, 'action', None), (context, REQUEST), \
                script.values( portal_status_message=str(message) ) )
            """
            context.redirect( action=action, message=str(message), frame=frame )

        message = "The file has been attached."
        action = 'attachfile, size %s' % str(len_file)

    elif pastefile:
        id = REQUEST['pastefile']
        # 'size' is used while generating an image preview thumbnail
        size = REQUEST.get('%s_size' % id, None)
        code = context.pasteFile(pastefile, size)
        if code == 1:
            message = "Link to the attachment has been inserted."
        elif code == -1:
            message = "Link to the attachment has been removed."
        action = 'pastefile%s' % ( size and ', size %s' % size or '')

    elif deletefile:
        context.removeFile( deletefile )
        message = "The attachment has been removed."
        action = 'deletefile'

    elif rm_associate:
        context.removeAssociation( rm_associate )
        message = "The association with attachment has been removed."
        action = 'rm_associate'

    elif associatefile:
        context.associateWithAttach( associatefile )
        message = "The association with attachment has been added."
        action = 'associatefile'

    elif lockfile:
        context.lockViewAttachment( lockfile )
        message = "The attachment has been locked."
        action = 'lockfile'

    elif unlockfile:
        context.unlockViewAttachment( unlockfile )
        message = "The attachment has been unlocked."
        action = 'unlockfile'

    # Update the document 'modification' date
    # todo: document.setEffectiveDate(DateTime())

    no_clean_html = not context.portal_membership.getInterfacePreferences('cleanup')
    context.cleanup( no_clean_html=no_clean_html )

    if log_message:
        ts = str(int(DateTime()))
        context.changes_log.append( { 'date' : ts, 'member' : username, 'comment': log_message } )

    # Update additional fields
    sheet = context.propertysheets.get('ext_metadata', None)
    if sheet:
       for prop in sheet.propertyIds():
            sheet.manage_changeProperties({ prop: REQUEST.get(prop,'') })

    IsError = 0

except 'EditingConflict', text:
    if using_fine_reader:
        message = context.msg( str(text) )
    else:
        return context.document_conflict_form( context, REQUEST=REQUEST )
    IsError = 1
except ResourceLockedError:
    message = "Since document is locked, it was not saved."
    ObjectIsLocked = 1
    IsError = 0
except SimpleError, msg:
    message = msg or 'Simple attachment error'
    IsError = 1
except Exception, error:
    if using_fine_reader:
        message = context.msg( str(formatErrorValue(Exception, error)))
    IsError = 1
    raise

CommitThread( context, 'document_edit: %s' % action, IsError, force=1, subtransaction=None )

end_time = DateTime()
UpdateRequestRuntime( context, username, start_time, end_time, 'document_edit %s' % (action and '[%s]' % action or '') )

if using_fine_reader:
    return context.msg( str(message) )

action = ( attachfile or deletefile or associatefile or rm_associate or lockfile or unlockfile ) and 'attachments' or \
    ObjectHasCustomCategory( document ) and 'view' or 'edit'

action = context.getTypeInfo().getActionById( action )

return context.redirect( action=action, message=message, frame=frame )
"""
return REQUEST.RESPONSE.redirect(
    context.absolute_url( redirect=1, action=action, message=message, frame=frame ),
    status=303 )
"""