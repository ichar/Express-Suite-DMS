## Script (Python) "invoke_factory"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=type_name, id, title=None, subject=None, description=None, language=None, type_args=None, cat_id=None, mail_type=None, upload=None, upload_id=None, nomencl_num=None, postfix=None, selected_template=None, source_registry=None
##title=Create content
##
from Products.ExpressSuiteTools.SecureImports import DateTime, SimpleError, InvalidIdError, cookId, \
     refreshClientFrame, parseTitle, parseDate, translit_string, check_unique_subject, \
     BeginThread, CommitThread, UpdateRequestRuntime, \
     SendToUsers, CustomDefs, portal_info, \
     departmentDictionary

REQUEST = context.REQUEST

start_time = DateTime()
member = context.portal_membership.getAuthenticatedMember()
username = member.getUserName()
message = ''

BeginThread( context, 'invoke_factory', force=1 )

IsManager = member is not None and member.has_role('Manager') and 1 or 0

title = parseTitle(title)
id = id.strip()

if upload:
    upload.seek(0,2)
    len_file = upload.tell()
    if len_file > 2048000 and not IsManager:
        return context.invoke_factory_form(context, REQUEST,
            **script.values( use_default_values=1, portal_status_message='Extra file uploading is not allowed.', 
            portal_status_style='error' ) )

IsHTMLBased = type_name in ( 'HTMLDocument', 'HTMLCard', ) and 1 or 0

if IsHTMLBased and not IsManager:
    if check_unique_subject( title, description ):
        return context.invoke_factory_form(context, REQUEST,
            **script.values( use_default_values=1, portal_status_message='Unique title and description.', 
            portal_status_style='error' ) )

if not id:
    create_as = translit_string( title.replace( ' ', '' ).strip(), 'ru').lower()
    if not title or ( len(title) == 1 and title in '\[\],./?''"!@#$%^&*()_+|-= \\' ):
        IsBadTitle = 1
    elif create_as in CustomDefs('bad_document_titles'):
        IsBadTitle = 1
    else:
        IsBadTitle = 0
    if IsBadTitle:
        return context.invoke_factory_form(context, REQUEST,
            **script.values( use_default_values=1, portal_status_message='Bad title or id.', 
            portal_status_style='error' ) )

    if IsHTMLBased:
        prefix = '_localtime_'
        size = 20
    else:
        prefix = None
        size = 20

    id = cookId( context, prefix=prefix, title=title, size=size )

if type_name == 'Mail Folder':
    if mail_type.startswith('fax'):
        type_name = 'Fax Incoming Folder'
    elif mail_type.startswith('in'):
        type_name == 'Incoming Mail Folder'
    else:
        type_name = 'Outgoing Mail Folder'

if type_args is None:
    type_args = ()

try:
    context.invokeFactory( type_name, id, None, *type_args )
except InvalidIdError, error:
    return apply( context.invoke_factory_form, (context, REQUEST),
            script.values( use_default_values=1, portal_status_message=str(error) ) )

ob = context[ id ]

if ob.implements('hasLanguage'):
    language = language or context.portal_membership.getLanguage()
    ob.setObjectLanguage(language)

ob.setTitle( title )

if subject is not None:
    subject = tuple( filter( None, subject ) )
    ob.setSubject(subject)

if description is not None:
    ob.setDescription(description)

if type_name is not None and cat_id is not None:
    ob.setCategory(cat_id)
    IsCategorial = 1
else:
    IsCategorial = 0

portal_info( 'invoke_factory: new object created by %s' % username, ( ob.getUid(), ob.physical_path() ) )

try:
    if IsCategorial:
        metadata = context.portal_metadata
        category = metadata.getCategoryById(cat_id)

        if category is not None:
            for attr in category.listAttributeDefinitions():
                name = attr.getId()
                linked_method = attr.getLinkedMethod()
                is_macro = name[:1] == '$' and 1 or 0

                if is_macro:
                    macro_ = name[1:]
                    if macro_ == 'template' and selected_template:
                        res = context.portal_catalog.searchResults( nd_uid=selected_template )
                        value = res and res[0]['Title']
                    elif macro_[0:7] == 'company':
                        company = member.getMemberCompany( mode='id' )
                        if macro_[8:] == 'name':
                            value = departmentDictionary.getCompanyTitle( company, 1 )
                        elif macro_[8:] == 'title':
                            value = departmentDictionary.getCompanyTitle( company )
                        else:
                            value = company
                    else:
                        continue
                else:
                    if attr.isHidden() or ( attr.isReadOnly() and not attr.isMandatory() ):
                        continue

                    if not REQUEST.has_key( name ):
                        if attr.isMandatory():
                            return context.invoke_factory_form(context, REQUEST,
                                **script.values( use_default_values=1, 
                                portal_status_message='Mandatory attribute missing') )
                            # raise 'Mandatory attribute missing'
                        continue

                    if attr.Type() == 'date':
                        value = parseDate( name, REQUEST, default=None  )
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
                    elif attr.Type() == 'items':
                        value = REQUEST.get( name, [] )
                    elif attr.Type() == 'userlist' or attr.getOptions('multiple'):
                        value = REQUEST.get( name, [] )
                        if value and value[0][:2] == 'x:':
                            x = value[0][2:]
                            value = x.split(':')
                    elif attr.Type() == 'table':
                        value = REQUEST.get( name, {} )
                        value = { 'count' : int(value.get('count') or 0), 'values' : [] }
                    else:
                        value = REQUEST.get( name, '' )

                if linked_method:
                    method = linked_method[0]

                    if method == 'SendToUsers':
                        attribute = linked_method[1]
                        linked_value = REQUEST.get( attribute, None )

                        try:
                            value = SendToUsers( ob, attribute, value, linked_value )
                        except:
                            pass

                ob.setCategoryAttribute( name, value, reindex=0 )

    if IsHTMLBased:
        # If we want to create document with template text
        if upload:
            try_to_associate=None #(category.getEditMode()=='')
            ob.addFile( id=upload_id, file=upload, try_to_associate=try_to_associate )
            if not try_to_associate and selected_template:
                category.applyDocumentTemplate( ob, selected_template )
        elif category.Template() and selected_template:
            category.applyDocumentTemplate( ob, selected_template )

    elif type_name == 'Heading':
        ob.setNomenclativeNumber( nomencl_num )
        ob.setPostfix( postfix )

    elif type_name == 'Registry':
        ob.CloneRegistry( source_registry )

    try: links = context.portal_links
    except: links = None

    if links is not None:
        links_to = REQUEST.get('links_to', [])
        source_uid = ob.getUid()
        for x in links_to:
            destination_uid = x.get('uid')
            source_ver_id = None
            if destination_uid:
                relation = x['relation']
                if ob.implements('isVersionable'):
                    source_ver_id = ob.getCurrentVersionId()

                links.createLink( source_uid=source_uid, destination_uid=destination_uid, relation=relation, \
                                  source_ver_id=source_ver_id, source=ob )

    ob.reindexObject()
    IsError = 0

#except KeyError:
#    raise

except SimpleError, msg:
    message = '%s $ $ error' % ( msg or 'Simple attachment error' )
    IsError = 1

except:
    message = 'Error was detected by invoke factory! $ $ error'
    IsError = 1

CommitThread( context, 'invoke_factory', IsError, force=1, subtransaction=None )

end_time = DateTime()
UpdateRequestRuntime( context, username, start_time, end_time, 'invoke_factory' )

refreshClientFrame('workspace')

if ob.implements('isPrincipiaFolderish'):
    refreshClientFrame('navTree')

info = context.portal_types.getTypeInfo( ob )
if not info.immediate_view:
    return context.redirect( action='folder', frame='inFrame', message="Object created." )

return ob.redirect( action=info.immediate_view, message=message )
