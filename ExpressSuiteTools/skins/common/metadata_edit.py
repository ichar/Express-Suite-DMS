## Script (Python) "metadata_edit"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=id,title=None,subject=None,description=None,language=None,contributors=None,effective_date=None,expiration_date=None,format=None,language=None,rights=None,type_name=None,category=None
##title=Update Content Metadata
##
from Products.ExpressSuiteTools.SecureImports import DateTime, refreshClientFrame, parseTitle, parseDate, \
     ResourceLockedError, Unauthorized, BeginThread, CommitThread, UpdateRequestRuntime, \
     SendToUsers, check_unique_subject, portal_info

REQUEST = context.REQUEST

start_time = DateTime()
member = context.portal_membership.getAuthenticatedMember()
username = member.getUserName()
message = ''

frame = context.meta_type == 'HTMLCard' and 'card_frame' or context.meta_type == 'HTMLDocument' and 'document_frame' or 'inFrame'

BeginThread( context, 'metadata_edit', force=1 )

IsManager = member is not None and member.has_role('Manager') and 1 or 0

def tuplify( value ):
    if not same_type( value, () ):
        value = tuple( value )
    temp = filter( None, value )
    return tuple( temp )

#get first non-version
ob = context
while ob.implements('isVersion'):
    ob = ob.aq_parent

# test for valid id (new)
if id != ob.getId():
    error = ob.aq_parent.checkId( id )
    if error:
        return apply( context.metadata_edit_form, (context, REQUEST), \
            script.values( portal_status_message=str(error) ) )

title = parseTitle(title or context.Title())

if subject is None:
    subject = context.Subject()
else:
    subject = tuplify( subject )

if description is None:
    description = '' # context.Description()

if not IsManager:
    if check_unique_subject( title, description ):
        return context.metadata_edit_form(context, REQUEST,
            **script.values( portal_status_message='Unique title and description.', portal_status_style='error' ) )

if language is not None and context.implements('hasLanguage'):
    context.setObjectLanguage(language)

if contributors is None:
    contributors = context.Contributors()
else:
    contributors = tuplify( contributors )

if effective_date is None:
    effective_date = context.EffectiveDate()

if expiration_date is None:
    expiration_date = context.expires()

if format is None:
    format = context.Format()

if language is None:
    language = context.Language()

if rights is None:
    rights = context.Rights()

if ob.implements('isCategorial') and not category:
    category = ob.Category()

portal_info( 'metadata_edit: object edited by %s' % username, ( ob.getUid(), ob.physical_path() ) )

try:
    if ob.implements('isCategorial') and category:
        if ob.Category() != category:
            ob.setCategory( category )

        metadata = context.portal_metadata
        document_category = metadata.getCategoryById(category)

        for attr in document_category.listAttributeDefinitions():
            name = attr.getId()

            if attr.isHidden() or ( attr.isReadOnly() and attr.isMandatory() ):
                continue
            
            if not REQUEST.has_key( name ):
                if attr.Type() == 'userlist':
                    value = []
                else:
                    continue

            linked_method = attr.getLinkedMethod()
            save_name = 'save_' + name

            if attr.Type() == 'date':
                value = REQUEST.get( name )
                if value[0:2] == '__':
                    pass
                else:
                    value = parseDate( name, REQUEST, default=None )
            elif attr.Type() == 'boolean':
                value = not not REQUEST.get( name )
            elif attr.Type() == 'link':
                get_default = attr.getComputedDefault() or [ 0 ]
                if get_default[0] == 1:
                    value = REQUEST.get( name, [] )
                elif get_default[0] == 2:
                    value = REQUEST.get( name, {} ).get('uid')
                else:
                    value = REQUEST.get( name ).uid
            elif attr.Type() in ['lines','items','userlist']:
                value = REQUEST.get( name, [] )
            elif attr.Type() == 'table':
                value = REQUEST.get( name, {} )
                value = { 'count' : int(value.get('count') or 0) }
            else:
                value = REQUEST.get( name, '' )

            if linked_method:
                method = linked_method[0]

                if method == 'SendToUsers':
                    attribute = linked_method[1]
                    linked_value = REQUEST.get( attribute, None )
                    saved_linked_value = REQUEST.get( 'save_%s' % attribute, None )

                    try:
                        value = SendToUsers( ob, attribute, value, linked_value, saved_linked_value )
                    except:
                        pass

            if REQUEST.has_key( save_name ):
                save_value = REQUEST.get( save_name, '' )
            else:
                continue
            
            if str(value) != str(save_value): 
                x = context.setCategoryAttribute( name, value, reindex=0 )

    try:
        ob.editMetadata( title=title
                       , description=description
                       , subject=subject
                       , contributors=contributors
                       , effective_date=effective_date
                       , expiration_date=expiration_date
                       , format=format
                       , language=language
                       , rights=rights
                       )

        if id and id != ob.getId():
            ob.aq_parent.manage_renameObject( ob.getId(), id )

    except Unauthorized:
        pass

    ob.reindexObject( idxs=['CategoryAttributes', 'SearchableText', 'Title', 'Description'] ) # , 'SearchableProperty'
    refreshClientFrame('workspace')
    message = "Metadata changed"
    IsError = 0

except ResourceLockedError:
    message = "Since document is locked, metadata was not changed."
    IsError = 1

CommitThread( context, 'metadata_edit', IsError, force=1, subtransaction=None )

end_time = DateTime()
UpdateRequestRuntime( context, username, start_time, end_time, 'metadata_edit' )

if REQUEST.get( 'change_and_edit', 0 ):
    action_id = 'edit'
elif REQUEST.get( 'change_and_view', 0 ):
    action_id = 'view'
else:
    action_id = 'metadata'

action = context.getTypeInfo().getActionById( action_id )

return context.redirect( action=action, message=message, frame=frame )
